"""SpaCy-backed PII detector. Flags text containing a PERSON named entity.

Detection runs inside ``nlp.memory_zone()``. This process is long-lived and reads
arbitrary search terms, whose token tail (typos, transliterations, product codes,
non-English words) never saturates. SpaCy is built for batch work and interns every
novel token it sees into the shared ``Vocab``: without the zone, each one costs a
permanent ``LexemeC`` plus its orth and norm strings in the ``StringStore``, measured
at ~487 bytes per token. The zone routes those to a scratch pool released when the
block exits.

The zone reclaims allocations but not the index capacity behind them: it retires
orths via preshed's ``map_clear``, which deliberately does not decrement the table's
``filled`` counter, so ``Vocab._by_orth`` and ``StringStore._map`` keep doubling
their capacity as though every retired slot were still occupied. That residual
measured ~31 bytes per novel token and does not plateau, so this process still grows
for as long as it runs -- just far more slowly. Only rebuilding the pipeline resets
those tables; that is deliberately not done here, so the footprint is expected to
creep and wants either headroom or a restart cadence to absorb it.

Note that ``len(nlp.vocab.strings)`` cannot detect that residual: it reports
``keys.size() + _transient_keys.size()``, neither of which tracks the ``_map``
table. Use RSS to check that claim, not the store's length.

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

    def __init__(self, model_name: str, excluded_components: list[str]) -> None:
        """Load the SpaCy model, auto-downloading it if not yet installed.

        Args:
            model_name: One of "en_core_web_sm", "en_core_web_md", "en_core_web_lg".
            excluded_components: SpaCy pipeline components to exclude at load time.
        """
        # A memory zone swaps `nlp.vocab.mem` for the duration of the block, so two
        # threads detecting at once could free one another's pool. The NER thread pool
        # is size-1 today (`pii.executor_max_workers`), which makes this lock
        # uncontended, but it is what keeps raising that setting from corrupting the
        # shared vocab rather than merely slowing detection down.
        self._zone_lock = threading.Lock()
        try:
            self.nlp = spacy.load(model_name, exclude=excluded_components)
        except OSError:
            logger.info("SpaCy model %s not found; downloading", model_name)
            spacy_download(model_name)
            self.nlp = spacy.load(model_name, exclude=excluded_components)

    def is_person(self, text: str) -> bool:
        """Return True iff `text` contains a PERSON named entity."""
        with self._zone_lock, self.nlp.memory_zone():
            return any(ent.label_ == PERSON_LABEL for ent in self.nlp(text).ents)

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
        with self._zone_lock, self.nlp.memory_zone():
            return [
                any(ent.label_ == PERSON_LABEL for ent in doc.ents)
                for doc in self.nlp.pipe(texts, batch_size=len(texts))
            ]


def build_detector(settings) -> PiiDetector:
    """Construct a PiiDetector from the merino-fleece Dynaconf settings."""
    return PiiDetector(
        model_name=settings.pii.model,
        excluded_components=list(settings.pii.excluded_components),
    )
