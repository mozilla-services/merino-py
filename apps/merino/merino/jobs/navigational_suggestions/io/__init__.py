"""I/O components for navigational suggestions job"""

from merino.jobs.navigational_suggestions.io.async_favicon_downloader import (
    AsyncFaviconDownloader,
)
from merino.jobs.navigational_suggestions.io.domain_data_downloader import (
    DomainDataDownloader,
)
from merino.jobs.navigational_suggestions.io.domain_metadata_diff import DomainDiff
from merino.jobs.navigational_suggestions.io.domain_metadata_uploader import (
    DomainMetadataUploader,
)

__all__ = [
    "AsyncFaviconDownloader",
    "DomainDataDownloader",
    "DomainMetadataUploader",
    "DomainDiff",
]
