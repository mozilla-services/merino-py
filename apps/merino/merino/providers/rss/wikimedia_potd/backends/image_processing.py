"""Image processing for Wikimedia Picture of the Day assets."""

import logging
from io import BytesIO

from PIL import Image as PILImage
from PIL import ImageOps

from merino.providers.rss.wikimedia_potd.backends.protocol import WikimediaPotdError
from merino.utils.gcs.models import Image

logger = logging.getLogger(__name__)

# Upper bound on the pixels the decoder is allowed to materialise, which is what the job
# pod's memory limit is really spent on. A decoded image holds ~3 bytes per pixel and the
# downscale allocates a further intermediate on top of that. The bound is on the decoded
# size rather than the source's nominal size because `draft()` below often decodes a very
# large JPEG at a fraction of its resolution, so the two can diverge sharply: a 16000x4000
# panorama decodes at 4MP and peaks at 173MB. 60MP rejects under 0.1% of pictures of the
# day. It also sits just above the most a JPEG can reach at all, 58.9MP, because draft()
# halves any source whose longest edge is twice the target; that worst case peaks at
# 621MB, inside the 1Gi cron pod limit. The bound therefore mostly guards the formats
# draft() cannot scale, such as PNG. Exceeding it skips the day's update and keeps the
# previous picture serving.
MAX_DECODED_PIXELS = 60_000_000


def _fitted_size(width: int, height: int, max_dimension: int) -> tuple[int, int]:
    """Scale `width` x `height` to fit a `max_dimension` square, never upscaling.

    Returns:
        The fitted dimensions, each at least one pixel.
    """
    scale = min(max_dimension / width, max_dimension / height, 1.0)

    return max(1, round(width * scale)), max(1, round(height * scale))


def process_potd_image(image: Image, max_dimension: int, webp_quality: int) -> Image:
    """Downscale a POTD image to fit within `max_dimension` and re-encode it as WebP.

    The aspect ratio is preserved and images already within bounds are never upscaled.
    The EXIF orientation is applied to the pixels, and all metadata except the ICC color
    profile is stripped from the output.

    Returns:
        An Image holding the WebP content. Raises WikimediaPotdError when the source
        cannot be decoded or decodes to more than MAX_DECODED_PIXELS.
    """
    try:
        # PIL's decompression bomb guard warns at ~89 megapixels, below routine POTD sizes,
        # so it is swapped for the explicit MAX_DECODED_PIXELS check below while open()
        # parses the header. The override is scoped to this call because the web service
        # imports this module and its guard must stay intact there. Nothing else in the potd
        # update job uses PIL concurrently.
        original_max_pixels = PILImage.MAX_IMAGE_PIXELS
        PILImage.MAX_IMAGE_PIXELS = None
        try:
            img = PILImage.open(BytesIO(image.content))
        finally:
            PILImage.MAX_IMAGE_PIXELS = original_max_pixels

        with img:
            source_width, source_height = img.size

            # decode JPEG sources at a reduced DCT scale (a no-op for other formats) so a
            # very large picture is never held at full resolution in memory. This only
            # records the scale to decode at. No pixels are materialised until they are
            # first accessed, which is why the bound below can be enforced before the
            # decode rather than after it.
            #
            # draft() halves only while the result stays at or above the size it is asked
            # for, so it has to be given the aspect-fitted target rather than the square
            # bounding box. Against the square box an elongated source is held back by its
            # short edge: a 16000x4000 panorama stays at its full 64MP, where the fitted
            # target lets the decoder run at 1/4 scale for 4MP.
            img.draft(img.mode, _fitted_size(source_width, source_height, max_dimension))

            if img.width * img.height > MAX_DECODED_PIXELS:
                raise WikimediaPotdError(
                    f"POTD image of {source_width}x{source_height} pixels decodes to "
                    f"{img.width}x{img.height}, over the {MAX_DECODED_PIXELS} pixel "
                    f"processing bound"
                )

            # downscale before transposing. The bounding box is square, so both orders
            # yield the same dimensions, but resizing first leaves the transpose working on
            # the small image rather than copying the full-resolution one.
            img.thumbnail((max_dimension, max_dimension), PILImage.Resampling.LANCZOS)

            # bake the EXIF orientation into the pixels since the tag is stripped on save
            ImageOps.exif_transpose(img, in_place=True)

            buffer = BytesIO()
            # the WebP encoder converts to RGB itself. EXIF and other metadata are dropped;
            # the ICC profile is kept so colors survive.
            img.save(
                buffer,
                format="WEBP",
                quality=webp_quality,
                icc_profile=img.info.get("icc_profile"),
            )
            processed_width, processed_height = img.size
    except OSError as ex:
        raise WikimediaPotdError(f"Failed to process POTD image: {ex}") from ex

    processed_image = Image(content=buffer.getvalue(), content_type="image/webp")

    logger.info(
        "Processed POTD image",
        extra={
            "source_dimensions": f"{source_width}x{source_height}",
            "processed_dimensions": f"{processed_width}x{processed_height}",
            "source_bytes": len(image.content),
            "processed_bytes": len(processed_image.content),
        },
    )

    return processed_image
