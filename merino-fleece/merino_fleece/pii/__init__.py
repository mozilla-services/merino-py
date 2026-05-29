"""PII / NER detection. Owns the singleton PiiDetector instance.

The detector is initialized once at app startup via :func:`init_detector` and
served to request handlers through :func:`get_detector` (used with FastAPI
``Depends``).
"""

import logging

from merino_fleece.configs import settings
from merino_fleece.pii.detector import PiiDetector, build_detector

logger = logging.getLogger(__name__)

_detector: PiiDetector | None = None


def init_detector() -> None:
    """Build the PiiDetector singleton from settings. Call once at startup."""
    global _detector
    _detector = build_detector(settings)


def shutdown_detector() -> None:
    """Drop the PiiDetector singleton. Call once at shutdown."""
    global _detector
    _detector = None


def get_detector() -> PiiDetector:
    """Return the initialized PiiDetector. Intended for use with ``fastapi.Depends``."""
    if _detector is None:
        raise RuntimeError("PiiDetector is not initialized; init_detector() must run first")
    return _detector
