"""Favicon processing components for navigational suggestions job"""

from merino.jobs.navigational_suggestions.favicon.favicon_extractor import FaviconExtractor
from merino.jobs.navigational_suggestions.favicon.favicon_processor import FaviconProcessor
from merino.jobs.navigational_suggestions.favicon.favicon_selector import FaviconSelector

__all__ = ["FaviconExtractor", "FaviconProcessor", "FaviconSelector"]
