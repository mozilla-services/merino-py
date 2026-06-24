"""Utility functions for parsing Wikimedia POTD RSS feed data."""

from bs4 import BeautifulSoup, Tag
from datetime import datetime
from feedparser import FeedParserDict
from pydantic import HttpUrl

from merino.providers.rss.wikimedia_potd.backends.protocol import PictureOfTheDay
from merino.utils.gcs.models import Image

# This is needed to prevent Wikimedia from blocking our requests as bot requests.
RSS_FETCH_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Merino/1.0; +https://github.com/mozilla-services/merino-py)"
}


def parse_potd(potd: FeedParserDict) -> PictureOfTheDay | None:
    """Parse the RSS entry description HTML to extract image URLs and text.

    Returns:
        A PictureOfTheDay instance if all required data is present, otherwise None.
    """
    title = str(potd.title)
    description = str(potd.description)

    # convert date to "2026-06-11" format from this format "Thu, 11 Jun 2026 00:00:00 GMT"
    published_date = datetime.strptime(str(potd.published), "%a, %d %b %Y %H:%M:%S %Z").strftime(
        "%Y-%m-%d"
    )

    parser = BeautifulSoup(description, "html.parser")

    img_tag = parser.find("img")

    # <img> tag is required to extract thumbnail url.
    if not isinstance(img_tag, Tag):
        return None

    thumbnail_url = img_tag.get("src")

    # Thumbnail url is required.
    if not thumbnail_url or not isinstance(thumbnail_url, str):
        return None

    # Wikimedia thumbnail URLs follow: /commons/thumb/{h1}/{h2}/{file}/{size}px-{file}
    # Removing "/thumb" and the trailing size segment gives the full-res URL.
    high_res_url = thumbnail_url.replace("/thumb", "").rsplit("/", 1)[0]

    # Extract plain text from the description div, stripping inner HTML.
    # Description text is optional.
    desc_div = parser.find("div", class_="description")
    description_text = (
        desc_div.get_text(separator=" ", strip=True) if isinstance(desc_div, Tag) else ""
    )

    return PictureOfTheDay(
        title=title,
        published_date=published_date,
        description=description_text,
        thumbnail_image_url=HttpUrl(thumbnail_url),
        high_res_image_url=HttpUrl(high_res_url),
    )


def extract_potd(parsed_feed: FeedParserDict) -> FeedParserDict | None:
    """Extract the latest valid entry from a parsed RSS feed.

    Returns:
        The latest entry if it contains the required fields, otherwise None.
    """
    # Malformed feed if entries property doesn't exist.
    if not parsed_feed.entries:
        return None

    potd = parsed_feed.entries[-1]

    # Malformed feed entry if the below properties don't exist.
    # The "description" entry contains the html that contain image urls and actual description text,
    # which is parsed in the parse_potd method.
    if not ("title" in potd and "description" in potd and "published" in potd):
        return None

    return potd


def build_potd_path_and_name(image: Image, is_thumbnail: bool) -> str:
    """Build the name string for a potd and prepend the bucket directory path to it."""
    # YYYY-MM-DD format
    date_time = datetime.today().strftime("%Y-%m-%d")

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
