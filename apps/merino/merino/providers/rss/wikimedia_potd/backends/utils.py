"""Utility functions for parsing Wikimedia Featured API picture of the day data."""

import re
from datetime import datetime, timedelta, timezone
from pydantic import HttpUrl

from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    PictureOfTheDayBase,
    WikimediaPotdError,
)

# Commons stores each language's POTD description on its own template subpage titled
# "Template:Potd/{date} ({lang})", so the trailing parenthesized code is the language.
# The bare "Template:Potd/{date}" page (the file selector) has no suffix and is ignored.
POTD_DESCRIPTION_LANG_RE = re.compile(r"\(([\w-]+)\)$")

# Image file extensions we accept for POTD assets.
POTD_IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})


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


def extract_image_description_with_lang_code(data: dict) -> tuple[str, str]:
    """Extract the image description language and text from a Wikimedia Featured API response.

    Returns:
        A (lang, text) tuple. Both are empty strings when the description is absent.
    """
    description = data.get("image", {}).get("description", {})
    return description.get("lang", ""), description.get("text", "")


def parse_discovered_languages(commons_data: dict) -> set[str]:
    """Extract POTD description language codes from a Commons allpages response.

    Returns:
        A set of discovered language codes, in the order returned by the API.
    """
    pages = commons_data.get("query", {}).get("allpages", [])

    discovered_languages: set[str] = set()

    for page in pages:
        match = POTD_DESCRIPTION_LANG_RE.search(page.get("title", ""))
        if match:
            discovered_languages.add(match.group(1))

    return discovered_languages


def build_potd_bucket_directory_path(date_str: str | None = None) -> str:
    """Build the dated gcs bucket directory path where a day's potd assets are stored.

    `date_str` is a YYYY-MM-DD date and defaults to today (UTC).
    """
    # YYYY-MM-DD format
    date_time = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"wikimedia_potd/{date_time}/"


def previous_day(date_str: str) -> str:
    """Return the calendar day before `date_str`, both in YYYY-MM-DD format."""
    return (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")


def as_previous_entry(potd: PictureOfTheDay | None) -> PictureOfTheDayBase | None:
    """Convert yesterday's manifest into the entry attached under today's `previous`.

    Yesterday's manifest carries its own `previous` from the day it was published. Dropping
    that field here is what keeps every published manifest exactly one day deep, instead of
    chaining back through each day the job has run.

    Returns:
        The narrowed entry, or None when yesterday has no manifest.
    """
    if potd is None:
        return None

    return PictureOfTheDayBase.model_validate(potd.model_dump(exclude={"previous"}))


def is_valid_potd_image_url(url: HttpUrl) -> bool:
    """Validate url is an image url. Only the url path is inspected, so thumbnail urls carrying a query string or fragment
    (e.g. the utm_* tracking params Wikimedia appends) are still recognized as images.
    """
    path = url.path or ""
    return path.rsplit(".", 1)[-1].lower() in POTD_IMAGE_EXTENSIONS
