"""Domain enrichment components for navigational suggestions job

This package contains custom domain lists, favicon overrides, and partner
integrations that supplement the main domain data from BigQuery.
"""

from merino.jobs.navigational_suggestions.enrichments.custom_domains import CUSTOM_DOMAINS
from merino.jobs.navigational_suggestions.enrichments.custom_favicons import (
    CUSTOM_FAVICONS,
    get_custom_favicon_url,
)
from merino.jobs.navigational_suggestions.enrichments.partner_favicons import PARTNER_FAVICONS

__all__ = [
    "CUSTOM_DOMAINS",
    "CUSTOM_FAVICONS",
    "get_custom_favicon_url",
    "PARTNER_FAVICONS",
]
