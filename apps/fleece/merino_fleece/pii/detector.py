"""SpaCy-backed PII detector. Flags text containing a PERSON named entity.

This process is long-lived and reads arbitrary search terms, whose token tail
(typos, transliterations, product codes, non-English words) never saturates. SpaCy
is built for batch work and interns every novel token it sees into the shared
``Vocab``, so left alone it grows for the life of the pod. Two mechanisms bound
that here, because neither is sufficient alone:

1. Detection runs inside ``nlp.memory_zone()``. Without it, each novel token costs a
   permanent entry in its internal cache. The zone routes those to a scratch pool that is
   released when the block exits.

2. The pipeline is reloaded every ``recycle_after_texts`` texts. The zone reclaims
   allocations but not index capacity, reloading handles that.

The zone makes any ``Doc`` created inside it invalid once the block exits, so the
methods below reduce each document to a ``bool`` before returning; they must never
hand a ``Doc``, ``Span``, or ``Token`` back to a caller.
"""

import logging
import threading

import spacy
from spacy.cli.download import download as spacy_download
from spacy.language import Language

logger = logging.getLogger(__name__)

PERSON_LABEL = "PERSON"


class PiiDetector:
    """Detect PII in text via SpaCy NER. PII == presence of a PERSON entity."""

    nlp: Language

    def __init__(
        self,
        model_name: str,
        excluded_components: list[str],
        recycle_after_texts: int = 0,
    ) -> None:
        """Load the SpaCy model, auto-downloading it if not yet installed.

        Args:
            model_name: One of "en_core_web_sm", "en_core_web_md", "en_core_web_lg".
            excluded_components: SpaCy pipeline components to exclude at load time.
            recycle_after_texts: Reload the pipeline once it has processed this many
                texts, discarding the index capacity a memory zone cannot reclaim.
                Zero disables recycling, which leaves the process growing slowly for
                as long as it runs.
        """
        self._model_name = model_name
        self._excluded_components = excluded_components
        self._recycle_after_texts = recycle_after_texts
        self._texts_since_load = 0
        # A memory zone swaps `nlp.vocab.mem` for the duration of the block, and a
        # recycle swaps `nlp` wholesale, so two threads detecting at once could free
        # one another's pool or model. The NER thread pool is size-1 today
        # (`pii.executor_max_workers`), which makes this lock uncontended, but it is
        # what keeps raising that setting from corrupting shared state rather than
        # merely slowing detection down.
        self._zone_lock = threading.Lock()
        self.nlp = self._load()

    def _load(self) -> Language:
        """Load the SpaCy pipeline, downloading the model on first use if needed."""
        try:
            return spacy.load(self._model_name, exclude=self._excluded_components)
        except OSError:
            logger.info("SpaCy model %s not found; downloading", self._model_name)
            spacy_download(self._model_name)
            return spacy.load(self._model_name, exclude=self._excluded_components)

    def _recycle_if_due(self, text_count: int) -> None:
        """Reload the pipeline once it has processed ``recycle_after_texts`` texts.

        Callers must hold ``_zone_lock`` and must not be inside a memory zone, since
        the zone's exit path reaches into the vocab this replaces.
        """
        if self._recycle_after_texts <= 0:
            return
        self._texts_since_load += text_count
        if self._texts_since_load < self._recycle_after_texts:
            return
        logger.info(
            "Recycling SpaCy pipeline to release retained index capacity",
            extra={"texts_since_load": self._texts_since_load},
        )
        self.nlp = self._load()
        self._texts_since_load = 0

    def is_person(self, text: str) -> bool:
        """Return True iff `text` contains a PERSON named entity."""
        with self._zone_lock:
            with self.nlp.memory_zone():
                verdict = any(ent.label_ == PERSON_LABEL for ent in self.nlp(text).ents)
            self._recycle_if_due(1)
            return verdict

    def is_person_batch(self, texts: list[str]) -> list[bool]:
        """Return, for each text, whether it contains a PERSON named entity.

        Batches the model's forward pass via SpaCy's ``nlp.pipe``, which is
        considerably cheaper than calling :meth:`is_person` once per text. Verdicts
        are returned in input order, as ``nlp.pipe`` preserves it.

        ``n_process`` is left at its default of 1: callers already run this in a
        worker thread and share a single loaded model, so forking processes would
        duplicate the model for no gain.
        """
        if not texts:
            return []
        with self._zone_lock:
            with self.nlp.memory_zone():
                verdicts = [
                    any(ent.label_ == PERSON_LABEL for ent in doc.ents)
                    for doc in self.nlp.pipe(texts, batch_size=len(texts))
                ]
            self._recycle_if_due(len(texts))
            return verdicts


def build_detector(settings) -> PiiDetector:
    """Construct a PiiDetector from the merino-fleece Dynaconf settings."""
    return PiiDetector(
        model_name=settings.pii.model,
        excluded_components=list(settings.pii.excluded_components),
        recycle_after_texts=settings.pii.recycle_after_texts,
    )
