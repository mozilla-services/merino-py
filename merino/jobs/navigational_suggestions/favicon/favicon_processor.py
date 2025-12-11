"""Favicon processor for downloading, validating, and uploading favicons"""

import logging
from typing import Any, TYPE_CHECKING

from merino.jobs.navigational_suggestions.constants import FAVICON_BATCH_SIZE
from merino.jobs.navigational_suggestions.favicon.favicon_selector import FaviconSelector
from merino.jobs.navigational_suggestions.utils import fix_url, is_valid_url
from merino.jobs.navigational_suggestions.io import AsyncFaviconDownloader

if TYPE_CHECKING:
    from merino.jobs.navigational_suggestions.io.domain_metadata_uploader import (
        DomainMetadataUploader,
    )

logger = logging.getLogger(__name__)


class FaviconProcessor:
    """Download, validate, and upload favicons. Prioritizes SVGs over bitmaps."""

    def __init__(
        self,
        favicon_downloader: AsyncFaviconDownloader,
        base_url: str = "",
    ) -> None:
        self.favicon_downloader = favicon_downloader
        self.base_url = base_url

    async def process_and_upload_best_favicon(
        self,
        favicons: list[dict[str, Any]],
        min_width: int,
        uploader: "DomainMetadataUploader",
    ) -> str:
        """Process and upload best favicon (SVGs first, then bitmaps if needed)."""
        try:
            # Filter and prepare URLs
            urls = [fix_url(favicon.get("href", ""), self.base_url) for favicon in favicons]
            urls = [url for url in urls if is_valid_url(url)]

            if not urls:
                return ""

            # Identify masked SVG indices upfront (to skip them)
            masked_svg_indices = [i for i, favicon in enumerate(favicons) if "mask" in favicon]

            # Categorize URLs by type
            svg_urls, svg_indices = self._categorize_svg_urls(urls)
            bitmap_urls, bitmap_indices = self._categorize_bitmap_urls(urls)

            # Phase 1: Process SVGs first (highest priority)
            svg_result = await self._process_svg_favicons(
                svg_urls, svg_indices, masked_svg_indices, uploader
            )
            if svg_result:
                return svg_result

            # Phase 2: Process bitmaps only if no suitable SVG found
            bitmap_result = await self._process_bitmap_favicons(
                bitmap_urls, bitmap_indices, favicons, min_width, uploader
            )

            return bitmap_result

        except Exception as e:
            logger.error(f"Unexpected error in process_and_upload_best_favicon: {e}")
            return ""

    def _categorize_svg_urls(self, urls: list[str]) -> tuple[list[str], list[int]]:
        """Extract SVG URLs and their indices."""
        svg_urls = []
        svg_indices = []

        for i, url in enumerate(urls):
            if url.lower().endswith(".svg"):
                svg_urls.append(url)
                svg_indices.append(i)

        return svg_urls, svg_indices

    def _categorize_bitmap_urls(self, urls: list[str]) -> tuple[list[str], list[int]]:
        """Extract non-SVG URLs and their indices."""
        bitmap_urls = []
        bitmap_indices = []

        for i, url in enumerate(urls):
            if not url.lower().endswith(".svg"):
                bitmap_urls.append(url)
                bitmap_indices.append(i)

        return bitmap_urls, bitmap_indices

    async def _process_svg_favicons(
        self,
        svg_urls: list[str],
        svg_indices: list[int],
        masked_svg_indices: list[int],
        uploader: "DomainMetadataUploader",
    ) -> str:
        """Process SVGs and return first valid, non-masked one."""
        if not svg_urls:
            return ""

        try:
            svg_images = await self.favicon_downloader.download_multiple_favicons(svg_urls)

            for local_idx, (image, url) in enumerate(zip(svg_images, svg_urls)):
                original_idx = svg_indices[local_idx]

                try:
                    if image is None or "image/svg+xml" not in image.content_type:
                        continue

                    # Skip masked SVGs (they're for specific UI contexts)
                    if original_idx in masked_svg_indices:
                        continue

                    # Upload and return immediately - SVGs are top priority
                    dst_favicon_name = uploader.destination_favicon_name(image)
                    try:
                        result = uploader.upload_image(image, dst_favicon_name, forced_upload=True)
                        return str(result)
                    except Exception as e:
                        logger.warning(f"Failed to upload SVG favicon: {e}")
                        # Fall back to original URL for SVG if upload fails
                        return url

                except Exception as e:
                    logger.warning(f"Exception processing SVG at position {local_idx}: {e}")
                finally:
                    if image:
                        del image

            del svg_images

        except Exception as e:
            logger.error(f"Error during SVG favicon processing: {e}")

        return ""

    async def _process_bitmap_favicons(
        self,
        bitmap_urls: list[str],
        bitmap_indices: list[int],
        all_favicons: list[dict[str, Any]],
        min_width: int,
        uploader: "DomainMetadataUploader",
    ) -> str:
        """Process bitmaps in batches and upload the best one meeting min_width."""
        if not bitmap_urls:
            return ""

        best_favicon_url = ""
        best_favicon_width = 0
        best_favicon_source = "default"

        try:
            # Process in batches to manage memory
            for i in range(0, len(bitmap_urls), FAVICON_BATCH_SIZE):
                batch_urls = bitmap_urls[i : i + FAVICON_BATCH_SIZE]
                batch_indices = bitmap_indices[i : i + FAVICON_BATCH_SIZE]

                try:
                    batch_images = await self.favicon_downloader.download_multiple_favicons(
                        batch_urls
                    )

                    for local_idx, (image, url) in enumerate(zip(batch_images, batch_urls)):
                        original_idx = batch_indices[local_idx]

                        try:
                            if image is None or "image/" not in image.content_type:
                                continue

                            # Get image dimensions
                            try:
                                width, height = image.get_dimensions()
                                width_val = min(width, height)
                            except Exception as e:
                                logger.warning(
                                    f"Exception getting dimensions at position {local_idx}: {e}"
                                )
                                continue

                            # Check if this is better than current best
                            if FaviconSelector.is_better_favicon(
                                all_favicons[original_idx],
                                width_val,
                                best_favicon_width,
                                best_favicon_source,
                            ):
                                try:
                                    dst_favicon_name = uploader.destination_favicon_name(image)
                                    favicon_url = uploader.upload_image(
                                        image, dst_favicon_name, forced_upload=True
                                    )
                                    best_favicon_url = favicon_url
                                    best_favicon_width = width_val
                                    best_favicon_source = all_favicons[original_idx].get(
                                        "_source", "default"
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to upload bitmap favicon: {e}")
                                    # Fallback to original URL if upload fails
                                    if FaviconSelector.is_better_favicon(
                                        all_favicons[original_idx],
                                        width_val,
                                        best_favicon_width,
                                        best_favicon_source,
                                    ):
                                        best_favicon_url = url
                                        best_favicon_width = width_val
                                        best_favicon_source = all_favicons[original_idx].get(
                                            "_source", "default"
                                        )

                        except Exception as e:
                            logger.warning(
                                f"Exception processing bitmap at position {local_idx}: {e}"
                            )
                        finally:
                            if image:
                                del image

                    del batch_images

                except Exception as e:
                    logger.error(f"Error processing bitmap batch: {e}")

            # Return the best favicon URL if it meets minimum width requirement
            return best_favicon_url if best_favicon_width >= min_width else ""

        except Exception as e:
            logger.error(f"Error during bitmap favicon processing: {e}")
            return ""
