"""Utility functions for parsing Wikimedia Featured API picture of the day data."""

from datetime import datetime, timezone
from pydantic import HttpUrl

from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPotdError,
)
from merino.utils.gcs.models import Image

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
    artist = image.get("artist", {})
    lic = image.get("license", {})
    file_page = image.get("file_page")

    return PictureOfTheDay(
        title=f"Wikimedia Commons Picture of the Day for {today:%B} {today.day}",
        published_date=today.strftime("%Y-%m-%d"),
        thumbnail_image_url=HttpUrl(thumbnail_url),
        high_res_image_url=HttpUrl(high_res_url),
        description=description.get("text", ""),
        author=artist.get("text", ""),
        file_page=HttpUrl(file_page) if file_page else None,
        license_label=lic.get("type", ""),
        license_link=HttpUrl(lic["url"]) if lic.get("url") else None,
    )


def build_potd_image_path(image: Image, is_thumbnail: bool) -> str:
    """Build the name string for a potd and prepend the bucket directory path to it."""
    # YYYY-MM-DD format
    date_time = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Under the bucket merino-images-prod, potd images are stored in the following directory.
    dir_path_in_bucket = "rss/wikimedia_potd"
    # append "_thumbnail" to the object name if it is a thumbnail image
    suffix = "thumbnail" if is_thumbnail else "hi_res"

    # extract image extension since the image.content_type has the format image/jpeg
    extension = image.content_type.split("/")[-1]

    # the path in the gcs bucket directory for the image would look like:
    # "rss/wikimedia_potd/POTD_2026-06-07_thumbnail.jpeg"
    return f"{dir_path_in_bucket}/POTD_{date_time}_{suffix}.{extension}"


def is_valid_potd_image_url(url: HttpUrl) -> bool:
    """Validate url is an image url."""
    return bool(str(url).split(".")[-1] in ["jpg", "jpeg", "png", "webp"])
