"""Image processing for Wikimedia Picture of the Day assets."""

import logging
from io import BytesIO

from PIL import Image as PILImage
from PIL import ImageOps

from merino.providers.rss.wikimedia_potd.backends.protocol import WikimediaPotdError
from merino.utils.gcs.models import Image

logger = logging.getLogger(__name__)

# A decoded image holds ~3 bytes per pixel in memory, so an unbounded source could OOM the
# job pod. Failing this check skips the day's update and keeps the previous picture serving.
MAX_SOURCE_PIXELS = 500_000_000


def process_potd_image(image: Image, max_dimension: int, webp_quality: int) -> Image:
    """Downscale a POTD image to fit within `max_dimension` and re-encode it as WebP.

    The aspect ratio is preserved and images already within bounds are never upscaled.
    The EXIF orientation is applied to the pixels, and all metadata except the ICC color
    profile is stripped from the output.

    Returns:
        An Image holding the WebP content. Raises WikimediaPotdError when the source
        cannot be decoded or is larger than MAX_SOURCE_PIXELS.
    """
    try:
        # PIL's decompression bomb guard warns at ~89 megapixels, below routine POTD sizes,
        # so it is swapped for the explicit MAX_SOURCE_PIXELS check below while open() parses
        # the header. The override is scoped to this call because the web service imports
        # this module and its guard must stay intact there; nothing else in the potd update
        # job uses PIL concurrently.
        original_max_pixels = PILImage.MAX_IMAGE_PIXELS
        PILImage.MAX_IMAGE_PIXELS = None
        try:
            img = PILImage.open(BytesIO(image.content))
        finally:
            PILImage.MAX_IMAGE_PIXELS = original_max_pixels

        with img:
            source_width, source_height = img.size
            if source_width * source_height > MAX_SOURCE_PIXELS:
                raise WikimediaPotdError(
                    f"POTD image of {source_width}x{source_height} pixels exceeds the "
                    f"{MAX_SOURCE_PIXELS} pixel processing bound"
                )

            # decode JPEG sources at a reduced DCT scale (a no-op for other formats) so a
            # very large picture is never held at full resolution in memory
            img.draft(img.mode, (max_dimension, max_dimension))

            # bake the EXIF orientation into the pixels since the tag is stripped on save
            processed = ImageOps.exif_transpose(img)

        # in-place downscale that preserves the aspect ratio and never upscales
        processed.thumbnail((max_dimension, max_dimension), PILImage.Resampling.LANCZOS)

        buffer = BytesIO()
        # the WebP encoder converts to RGB itself, keeping alpha when present. EXIF and
        # other metadata are dropped; the ICC profile is kept so colors survive.
        processed.save(
            buffer,
            format="WEBP",
            quality=webp_quality,
            icc_profile=processed.info.get("icc_profile"),
        )
    except OSError as ex:
        raise WikimediaPotdError(f"Failed to process POTD image: {ex}") from ex

    processed_image = Image(content=buffer.getvalue(), content_type="image/webp")

    logger.info(
        "Processed POTD image",
        extra={
            "source_dimensions": f"{source_width}x{source_height}",
            "processed_dimensions": f"{processed.width}x{processed.height}",
            "source_bytes": len(image.content),
            "processed_bytes": len(processed_image.content),
        },
    )

    return processed_image
