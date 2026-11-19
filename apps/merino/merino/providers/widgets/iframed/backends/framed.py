"""Framed Widgets backend."""

import aiodogstatsd
import asyncio
import logging
import semver

from pydantic import HttpUrl

from gcloud.aio.storage import Bucket, Storage

from merino.configs import settings
from merino.providers.widgets.iframed.backends.protocol import (
    FramedWidgetResponse,
    FramedWidgetGCS,
)
from merino.providers.widgets.iframed.backends.widgets_manifest import build_manifest
from merino.utils import task_runner

logger = logging.getLogger(__name__)

_fetch_widgets_timeout = settings.widgets.providers.framed.fetch_widgets_timeout

_ASYNC_TASK_NAME_PREFIX = "widgets.framed."


class FramedWidgetsBackend:
    """Backend for fetching the latest release URLs for all framed widgets."""

    gcs_client: Storage
    cached_widgets: dict[str, FramedWidgetResponse]
    metrics_client: aiodogstatsd.Client
    widgets_manifest: list[FramedWidgetGCS]

    def __init__(
        self,
        gcs_client: Storage,
        metrics_client: aiodogstatsd.Client,
    ) -> None:
        """Initialize the backend."""
        self.gcs_client = gcs_client
        # store results of the previous fetch as a backup cache should the next fetch fail for any particular widgets
        self.cached_widgets = {}
        self.metrics_client = metrics_client
        self.widgets_manifest = build_manifest()

    async def fetch(self) -> list[FramedWidgetResponse]:
        """Fetch framed widget data from GCS."""
        response: list[FramedWidgetResponse] = []

        # batch up fetching latest widgets
        wrapped_tasks = [
            asyncio.create_task(
                self._build_widget_response(widget),
                name=f"{_ASYNC_TASK_NAME_PREFIX}{widget.id}",
            )
            for widget in self.widgets_manifest
        ]

        # wait for all widget fetches to complete
        await task_runner.gather(
            wrapped_tasks,
            timeout=_fetch_widgets_timeout,
            timeout_cb=self.metrics_timeout_handler,
        )

        # merge widgets manifest and wrapped tasks as tuples.
        # as wrapped_tasks is built from widgets_manifest, they are essentially pre/post
        # representations of the data.
        for widget, task in zip(self.widgets_manifest, wrapped_tasks):
            # if the async task completed (and wasn't cancelled due to timeout), store the task result. otherwise (if the task isn't done or was cancelled), the result is None.
            fresh_widget = task.result() if task.done() and not task.cancelled() else None

            # determine if we should return the fresh widget (if exists) or the cached version (also if exists).
            # if neither exist, the widget is omitted from the response.
            if fresh_widget is not None:
                # if the fresh_widget exists, store it in the cache and add it to the response
                self.cached_widgets[widget.id] = fresh_widget

                response.append(fresh_widget)
            elif (cached_widget := self.cached_widgets.get(widget.id)) is not None:
                # otherwise, if the widget has a cached version, log a warning and add the cached widget to the response
                logger.warning(
                    "Framed widget fetch failed, returning cached version",
                    extra={"id": widget.id, "url": str(cached_widget.url)},
                )

                # keep a tally of how often a cached widget is served
                self.metrics_client.increment(
                    "providers.widgets.framed.stale", tags={"widget": widget.id}
                )

                response.append(cached_widget)

        return response

    def metrics_timeout_handler(self, tasks: list[asyncio.Task]) -> None:
        """Timeout handler to record metrics for timed out tasks"""
        for task in tasks:
            widget_id = task.get_name().removeprefix(_ASYNC_TASK_NAME_PREFIX)

            self.metrics_client.increment(
                "providers.widgets.framed.query.timeout", tags={"widget": widget_id}
            )

    async def _build_widget_response(self, widget: FramedWidgetGCS) -> FramedWidgetResponse | None:
        """Retrieve the latest semver for the given framed widget and returns a FramedWidgetResponse, or None in the case of error."""
        try:
            latest_semver = await self._get_latest_semver_from_gcs(widget.bucket_name)

            # build the public URL
            url = FramedWidgetsBackend.build_public_url(widget.cdn_host, latest_semver)

            return FramedWidgetResponse(
                enabled=widget.enabled, id=widget.id, vendor=widget.vendor, url=url
            )
        except Exception as e:
            logger.warning(
                "Error retrieving latest semver for framed widget",
                extra={"id": widget.id, "bucket": widget.bucket_name, "error": str(e)},
            )
            return None

    async def _get_latest_semver_from_gcs(self, bucket_name: str) -> str:
        """Return latest semver release from the given GCS bucket_name."""
        gcs_folders = await self._get_bucket_folders(bucket_name=bucket_name)

        highest_semver = FramedWidgetsBackend.get_highest_semver(gcs_folders)

        # if no semver folder was found, raise (handled by calling function)
        if highest_semver is None:
            raise ValueError("No release folders found.")

        return highest_semver

    async def _get_bucket_folders(self, bucket_name: str) -> set[str]:
        """Retrieve all folders (blobs with a trailing "/") in the given GCS bucket."""
        bucket = Bucket(storage=self.gcs_client, name=bucket_name)
        blobs = await bucket.list_blobs(delimiter="/")

        # list_blobs returns all the files "left" of the given delimiter, even if
        # they don't end with the delimiter - keeping the list restricted to only
        # "root" files and "folders" (GCS doesn't really have folders) as we don't
        # want to return any files within folders. that being said, as we only
        # want folders here, we filter out the result set to items ending with "/".
        #
        # and one more "blob" for good measure.
        return {blob for blob in blobs if blob.endswith("/")}

    @staticmethod
    def get_highest_semver(releases: set[str]) -> str | None:
        """Filter a set of strings to only those matching a semver naming convention and return the highest version."""
        # filter out any non-valid semver names, and remove any trailing slashes
        # (slashes are included in the GCS response)
        semver_strings = [r.strip("/") for r in releases if semver.Version.is_valid(r.strip("/"))]

        if len(semver_strings) == 0:
            return None

        # convert strings to Version objects for comparison below
        all_semvers = [semver.Version.parse(ss) for ss in semver_strings]

        # filter out any pre-release or build versions just in case
        semvers = [s for s in all_semvers if s.prerelease is None and s.build is None]

        # if we only found pre-release and build versions, there are no valid versions for this widget
        if len(semvers) == 0:
            return None

        # return the highest version as a string
        return str(max(semvers))

    @staticmethod
    def build_public_url(cdn_host: str, semver: str) -> HttpUrl:
        """Construct a public URL for the given semver folder."""
        # convention for framed widgets is a single index.html entrypoint
        if cdn_host == "" or semver == "":
            raise ValueError("Cannot build public URL for widget - host or semver is missing.")

        return HttpUrl(f"https://{cdn_host}/{semver}/index.html")
