"""SpaCy-backed PII detector. Flags text containing a PERSON named entity."""

import logging

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
        try:
            self.nlp = spacy.load(model_name, exclude=excluded_components)
        except OSError:
            logger.info("SpaCy model %s not found; downloading", model_name)
            spacy_download(model_name)
            self.nlp = spacy.load(model_name, exclude=excluded_components)

    def is_person(self, text: str) -> bool:
        """Return True iff `text` contains a PERSON named entity."""
        doc = self.nlp(text)
        return any(ent.label_ == PERSON_LABEL for ent in doc.ents)


def build_detector(settings) -> PiiDetector:
    """Construct a PiiDetector from the merino-fleece Dynaconf settings."""
    return PiiDetector(
        model_name=settings.pii.model,
        excluded_components=list(settings.pii.excluded_components),
    )
