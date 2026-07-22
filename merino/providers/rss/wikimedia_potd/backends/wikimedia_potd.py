"""Wikimedia Picture of the Day backend."""

import logging
import aiodogstatsd
from datetime import datetime, timezone
from pydantic import HttpUrl
from httpx import AsyncClient, HTTPError, Response
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from merino.configs import settings
from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPotdError,
)
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image
from merino.providers.rss.wikimedia_potd.backends.utils import (
    WIKIMEDIA_REQUEST_HEADERS,
    parse_potd,
    extract_image_description_with_lang_code,
    parse_discovered_languages,
    build_potd_bucket_directory_path,
    is_valid_potd_image_url,
)
import sentry_sdk

logger = logging.getLogger(__name__)


class WikimediaPictureOfTheDayBackend:
    """Backend for fetching the Wikimedia Picture of the Day from the Featured API."""

    metrics_client: aiodogstatsd.Client
    http_client: AsyncClient
    gcs_uploader: GcsUploader

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient,
        featured_api_base: str,
        commons_api_url: str,
        gcs_uploader: GcsUploader,
    ) -> None:
        """Initialize the backend with the Featured API base url and Commons discovery url."""
        self.featured_api_base = featured_api_base
        self.commons_api_url = commons_api_url
        self.metrics_client = metrics_client
        self.http_client = http_client
        self.gcs_uploader = gcs_uploader
        self.cache_control = settings.rss_providers.wikimedia_potd.cache_control

    async def upload_picture_of_the_day(self) -> bool:
        """Orchestrates fetching the Featured API, extracting the Picture of the Day (POTD),
        downloading and uploading images, and generating and uploading the POTD JSON manifest.

        Returns:
            Bool. True if success, False if failure.
        """
        # This is the single error boundary for the upload job: every helper below either
        # returns a value or raises, and any failure is reported to Sentry once here.
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # discover which languages have an authored description for today's picture
            languages = await self.discover_languages(today)

            # fetch the default (en) response for the image urls and base metadata
            potd_en = await self.fetch_picture_of_the_day("en")

            # parse the response to extract a PictureOfTheDay instance
            potd = parse_potd(potd_en)

            # collect localized image descriptions keyed by language; "en" is already excluded
            # during discovery (it is the default description), so this maps only non-English
            # languages and is empty when no localized descriptions exist
            localized_descriptions = await self.fetch_localized_descriptions(languages)

            # download thumbnail and high resolution images and get the respective cdn urls
            thumbnail_url, hi_res_url = await self.download_and_upload_potd_images(potd)

            potd_to_upload = potd.model_copy(
                update={
                    "thumbnail_image_url": thumbnail_url,
                    "high_res_image_url": hi_res_url,
                    "localized_descriptions": localized_descriptions,
                }
            )

            self.upload_potd_manifest(potd_to_upload)

            return True
        except Exception as ex:
            sentry_sdk.capture_exception(ex)
            return False

    async def discover_languages(self, date_str: str) -> set[str]:
        """Discover the languages with an authored POTD description for `date_str`.

        Queries the Wikimedia Commons allpages API for the "Template:Potd/{date} ({lang})"
        subpages that exist for the day. The default language (en) is excluded because it is
        already the default description on the potd. A discovery failure degrades to an empty
        set (logged, not raised) rather than failing the upload.

        Returns:
            A set of language codes with an authored description, excluding en.
        """
        params = {
            "action": "query",
            "format": "json",
            "list": "allpages",
            "apprefix": f"Potd/{date_str}",
            "apnamespace": "10",
            "aplimit": "500",
        }

        discovered_languages: set[str] = set()

        try:
            response: Response = await self.http_client.get(
                self.commons_api_url, params=params, headers=WIKIMEDIA_REQUEST_HEADERS
            )
            response.raise_for_status()
            discovered_languages.update(parse_discovered_languages(response.json()))

            # "en" is the default description already on the potd, so never fetch it again
            discovered_languages.discard("en")

        except Exception as ex:
            logger.warning(
                "Failed to discover POTD description languages",
                extra={"error": str(ex), "date": date_str},
            )

        return discovered_languages

    async def fetch_localized_descriptions(self, languages: set[str]) -> dict[str, str]:
        """Fetch a description for each language, keeping only genuinely localized text.

        "en" is excluded upstream by `discover_languages` because its description is already
        the default on the potd object. For every other language the Featured API silently
        returns the English description when no localization exists, so a response whose
        description comes back as "en" is dropped rather than stored as a duplicate.

        Returns:
            A mapping of language code to localized description text.
        """
        localized_descriptions: dict[str, str] = {}

        for lang in languages:
            try:
                potd_in_lang = await self.fetch_picture_of_the_day(lang)
                lang_code, description = extract_image_description_with_lang_code(potd_in_lang)
            except Exception as ex:
                logger.warning(
                    "Failed to fetch localized POTD description",
                    extra={"error": str(ex), "lang": lang},
                )
                continue

            # wikimedia featured api call returns English description as a fallback,
            # making sure not to add duplicate English descriptions as we have it on the default potd already.
            # so a call for potd to the Featured API, in Italian ("it"),
            # could return the fall back "en" version even if the language discovery call returned with "it"
            # as one of the supported languages for this potd.
            if description and lang_code != "en":
                localized_descriptions[lang_code] = description

        return localized_descriptions

    async def download_and_upload_potd_images(
        self, potd: PictureOfTheDay
    ) -> tuple[HttpUrl, HttpUrl]:
        """Download and upload potd thumbnail and high resolution images.

        Returns:
            tuple[HttpUrl, HttpUrl]. Raises WikimediaPotdError on failure.
        """
        # download thumbnail and high resolution images for the above potd instance
        thumbnail_image = await self.download_potd_image(potd.thumbnail_image_url)
        hi_res_image = await self.download_potd_image(potd.high_res_image_url)

        # upload thumbnail and high resolution images to the gcs bucket / cdn
        thumbnail_cdn_url = self.upload_potd_image(image=thumbnail_image, is_thumbnail=True)
        hires_cdn_url = self.upload_potd_image(image=hi_res_image, is_thumbnail=False)

        return (HttpUrl(thumbnail_cdn_url), HttpUrl(hires_cdn_url))

    @retry(
        wait=wait_exponential_jitter(
            initial=settings.rss_providers.wikimedia_potd.retry_wait_initial_seconds,
            jitter=settings.rss_providers.wikimedia_potd.retry_wait_jitter_seconds,
        ),
        stop=stop_after_attempt(settings.rss_providers.wikimedia_potd.retry_count),
        # retry on read/connect timeouts, connection resets, 5xx,
        # all HTTPError, empty/invalid-body responses that may recover
        retry=retry_if_exception_type((HTTPError, WikimediaPotdError)),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.INFO),
    )
    async def fetch_picture_of_the_day(self, lang: str) -> dict:
        """Fetch the Wikimedia Featured API picture of the day for today in `lang`.

        Retries transient failures with exponential backoff before giving up; the final
        failure is re-raised so the upload job's error boundary reports it once.

        Returns:
            The parsed JSON response as a dict. Raises WikimediaPotdError on failure.
        """
        # setting the format to YYYY/MM/DD which is accepted as the url param
        today = datetime.now(timezone.utc).strftime("%Y/%m/%d")

        # the Featured API expects lang and date in the url path: .../{lang}/featured/{yyyy}/{mm}/{dd}
        url = f"{self.featured_api_base}/{lang}/featured/{today}"

        response: Response = await self.http_client.get(url, headers=WIKIMEDIA_REQUEST_HEADERS)

        response.raise_for_status()

        if not response.content:
            raise WikimediaPotdError("Wikimedia POTD featured api returned empty content")

        try:
            data: dict = response.json()
        except ValueError as ex:
            raise WikimediaPotdError("Wikimedia POTD featured api returned invalid JSON") from ex

        return data

    async def download_potd_image(self, url: HttpUrl) -> Image:
        """Download the image using the image URL.

        Returns:
            An Image object containing the binary content and content type.
            Raises WikimediaPotdError on failure.
        """
        if not is_valid_potd_image_url(url):
            raise WikimediaPotdError(f"Invalid Wikimedia POTD image url: {url}")

        # set up request headers to only accept image content types
        request_headers = {
            **WIKIMEDIA_REQUEST_HEADERS,
            "accept": "image/jpeg,image/png,image/webp",
        }
        response: Response = await self.http_client.get(str(url), headers=request_headers)
        response.raise_for_status()

        content = response.content
        content_type = response.headers["content-type"]

        return Image(
            content=content,
            content_type=str(content_type),
        )

    def upload_potd_image(self, image: Image, is_thumbnail: bool) -> str:
        """Upload an image to the bucket.

        Returns:
            Public gcs bucket cdn url (str) of the uploaded image.
            Raises WikimediaPotdError if the image fails to upload.
        """
        # name the image file "thumbnail" or "hi_res" depending on the image variant
        suffix = "thumbnail" if is_thumbnail else "hi_res"

        # extract image extension since the image.content_type has the format image/jpeg
        extension = image.content_type.split("/")[-1]

        # path for a thumbnail image will look like: "wikimedia_potd/2026-06-07/thumbnail.jpeg
        potd_image_path = f"{build_potd_bucket_directory_path()}{suffix}.{extension}"

        # return a public cdn url for the image after a successful upload
        public_url = self.gcs_uploader.upload_image(
            image=image, destination_name=potd_image_path, cache_control=self.cache_control
        )

        # GcsUploader.upload_content swallows storage errors and returns a public url regardless,
        # so confirm the object actually landed in the bucket and fail loudly otherwise.
        if self.gcs_uploader.get_file_by_name(potd_image_path) is None:
            raise WikimediaPotdError(f"Failed to upload POTD image: {potd_image_path}")

        return public_url

    def upload_potd_manifest(self, potd: PictureOfTheDay) -> None:
        """Build and upload a PictureOfTheDay object to the gcs bucket.

        Raises WikimediaPotdError if the manifest fails to upload.
        """
        # manifest json is just the PictureOfTheDay model in json format
        manifest_json = potd.model_dump_json()
        # path for the potd will look like: "wikimedia_potd/2026-06-07/potd.json
        destination_name = f"{build_potd_bucket_directory_path()}potd.json"

        self.gcs_uploader.upload_content(
            content=manifest_json,
            destination_name=destination_name,
            content_type="application/json",
            forced_upload=True,
        )

        # GcsUploader.upload_content swallows storage errors, so confirm the object actually
        # landed in the bucket and fail loudly otherwise.
        if self.gcs_uploader.get_file_by_name(destination_name) is None:
            raise WikimediaPotdError(f"Failed to upload POTD manifest: {destination_name}")

    def fetch_potd_from_gcs_bucket(self) -> PictureOfTheDay | None:
        """Fetch the PictureOfTheDay object from the gcs bucket.

        Returns:
            A PictureOfTheDay object if available, otherwise None.
        """
        try:
            blob = self.gcs_uploader.get_file_by_name(
                f"{build_potd_bucket_directory_path()}potd.json"
            )

            if blob:
                potd_json = blob.download_as_text()
                return PictureOfTheDay.model_validate_json(potd_json)
        except Exception as ex:
            sentry_sdk.capture_exception(ex)

        return None

    async def shutdown(self) -> None:
        """Shutdown the backend.

        Returns:
            None.
        """
        await self.http_client.aclose()
