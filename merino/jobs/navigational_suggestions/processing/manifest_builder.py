"""Manifest builder for constructing top picks and partner manifests"""

import base64
from hashlib import md5
from typing import Optional

from httpx import URL

from merino.utils.domain_categories.domain_category_mapping import DOMAIN_MAPPING
from merino.utils.domain_categories.models import Category


def get_serp_categories(domain_url: str | None) -> list[int] | None:
    """Get SERP categories for domain URL using MD5 hash lookup."""
    if domain_url:
        url = URL(domain_url)
        md5_hash = md5(url.host.encode(), usedforsecurity=False).digest()
        return [
            category.value
            for category in DOMAIN_MAPPING.get(
                base64.b64encode(md5_hash).decode(), [Category.Inconclusive]
            )
        ]
    return None


def construct_top_picks(
    domain_data: list[dict],
    domain_metadata: list[dict[str, Optional[str]]],
) -> dict[str, list[dict[str, str]]]:
    """Combine domain data with extracted metadata to create top picks manifest.

    Custom domains without favicons are excluded. Top-picks domains are always
    included even without favicons.
    """
    result = []

    # Use zip to prevent IndexError when domain_metadata is shorter
    for domain, metadata in zip(domain_data, domain_metadata):
        if metadata["url"]:
            # Don't add custom domains without favicons, but keep top-picks
            if metadata["icon"] == "" and domain.get("source") != "top-picks":
                continue

            domain_url = metadata["url"]
            result.append(
                {
                    "rank": domain["rank"],
                    "domain": metadata["domain"],
                    "categories": domain["categories"],
                    "serp_categories": get_serp_categories(domain_url),
                    "url": domain_url,
                    "title": metadata["title"],
                    "icon": metadata["icon"],
                    "source": domain.get("source", "top-picks"),
                }
            )
    return {"domains": result}


def construct_partner_manifest(
    partner_favicon_source: list[dict[str, str]],
    uploaded_favicons: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Map partner domains to their original and GCS favicon URLs."""
    if len(partner_favicon_source) != len(uploaded_favicons):
        raise ValueError("Mismatch: The number of favicons and GCS URLs must be the same.")

    result = [
        {
            "domain": item["domain"],
            "url": item["url"],
            "original_icon_url": item["icon"],
            "gcs_icon_url": gcs_url,
        }
        for item, gcs_url in zip(partner_favicon_source, uploaded_favicons)
    ]

    return {"partners": result}
