"""Utility functions for parsing Wikimedia Featured API picture of the day data."""

from datetime import datetime, timezone
from pydantic import HttpUrl

from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPotdError,
)

# This is needed to prevent Wikimedia from blocking our requests as bot requests.
WIKIMEDIA_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Merino/1.0; +https://github.com/mozilla-services/merino-py)"
}


def parse_potd(data: dict) -> PictureOfTheDay:
    """Parse the Wikimedia Featured API response into a PictureOfTheDay.

    Returns:
        A PictureOfTheDay instance. Raises WikimediaPotdError if required data is missing.
    """
    image = data.get("image")
    if not image:
        raise WikimediaPotdError("Wikimedia potd featured response missing 'image'")

    # The Featured API returns both the thumbnail and full-res source urls directly.
    thumbnail_url = image.get("thumbnail", {}).get("source")
    high_res_url = image.get("image", {}).get("source")
    if not thumbnail_url or not high_res_url:
        raise WikimediaPotdError("Wikimedia potd missing image source url(s)")

    today = datetime.now(timezone.utc)
    description = image.get("description", {})
    # this field gets mapped to "author"
    artist = image.get("artist", {}).get("text", "")
    lic = image.get("license", {})
    file_page = image.get("file_page")

    return PictureOfTheDay(
        title=f"Wikimedia Commons Picture of the Day for {today:%B} {today.day}",
        published_date=today.strftime("%Y-%m-%d"),
        thumbnail_image_url=HttpUrl(thumbnail_url),
        high_res_image_url=HttpUrl(high_res_url),
        description=description.get("text", ""),
        # truncate author name if more than 50 chars
        author=artist[0:50] + "..." if len(artist) > 50 else artist,
        file_page=HttpUrl(file_page) if file_page else None,
        license_label=lic.get("type", ""),
        license_link=HttpUrl(lic["url"]) if lic.get("url") else None,
    )


def build_potd_bucket_directory_path() -> str:
    """Build the dated gcs bucket directory path where today's potd assets are stored."""
    # YYYY-MM-DD format
    date_time = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # the directory in the gcs bucket for today's POTD assets looks like:
    # "rss/wikimedia_potd/2026-06-07/"
    return f"rss/wikimedia_potd/{date_time}/"


def is_valid_potd_image_url(url: HttpUrl) -> bool:
    """Validate url is an image url."""
    return bool(str(url).split(".")[-1] in ["jpg", "jpeg", "png", "webp"])
