# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for Wikimedia POTD image processing."""

from io import BytesIO

import pytest
from PIL import Image as PILImage
from pytest_mock import MockerFixture

from merino.providers.rss.wikimedia_potd.backends.image_processing import process_potd_image
from merino.providers.rss.wikimedia_potd.backends.protocol import WikimediaPotdError
from merino.utils.gcs.models import Image

# EXIF tag id for the image orientation.
EXIF_ORIENTATION_TAG = 0x0112


def make_image(
    width: int, height: int, image_format: str = "JPEG", mode: str = "RGB", **save_kwargs
) -> Image:
    """Return an Image with generated content of the given dimensions and format."""
    buffer = BytesIO()
    with PILImage.new(mode, (width, height)) as img:
        img.save(buffer, format=image_format, **save_kwargs)

    return Image(content=buffer.getvalue(), content_type=f"image/{image_format.lower()}")


def open_processed(image: Image) -> PILImage.Image:
    """Open the content of a processed Image with PIL."""
    return PILImage.open(BytesIO(image.content))


class TestProcessPotdImage:
    """Tests for the process_potd_image function."""

    @pytest.mark.parametrize(
        ("source_size", "expected_size"),
        [
            ((800, 400), (200, 100)),
            ((400, 800), (100, 200)),
            ((200, 200), (200, 200)),
            ((120, 80), (120, 80)),
        ],
        ids=["downscales_landscape", "downscales_portrait", "keeps_exact_fit", "never_upscales"],
    )
    def test_bounds_the_longest_edge_preserving_aspect_ratio(
        self, source_size: tuple[int, int], expected_size: tuple[int, int]
    ) -> None:
        """Downscales images to fit max_dimension without upscaling smaller ones."""
        result = process_potd_image(make_image(*source_size), max_dimension=200, webp_quality=75)

        with open_processed(result) as img:
            assert img.size == expected_size

    def test_re_encodes_as_webp(self) -> None:
        """Returns WebP content with the matching content type regardless of source format."""
        result = process_potd_image(
            make_image(50, 50, image_format="PNG"), max_dimension=200, webp_quality=75
        )

        assert result.content_type == "image/webp"
        with open_processed(result) as img:
            assert img.format == "WEBP"

    def test_applies_exif_orientation_and_strips_metadata(self) -> None:
        """Bakes the EXIF orientation into the pixels and drops the EXIF metadata itself."""
        exif = PILImage.Exif()
        # orientation 6 means "rotate 90 degrees clockwise to display", so the 200x100 source
        # below must come out as 100x200
        exif[EXIF_ORIENTATION_TAG] = 6

        result = process_potd_image(
            make_image(200, 100, exif=exif), max_dimension=300, webp_quality=75
        )

        with open_processed(result) as img:
            assert img.size == (100, 200)
            assert not img.getexif()

    def test_applies_exif_orientation_when_also_downscaling(self) -> None:
        """Fits the bounding box in the displayed orientation, not the stored one.

        The downscale runs before the transpose, so a rotating orientation has to survive
        being applied to an already-resized image.
        """
        exif = PILImage.Exif()
        exif[EXIF_ORIENTATION_TAG] = 6

        result = process_potd_image(
            make_image(800, 400, exif=exif), max_dimension=200, webp_quality=75
        )

        with open_processed(result) as img:
            assert img.size == (100, 200)

    def test_raises_for_undecodable_content(self) -> None:
        """Raises WikimediaPotdError when the content is not a decodable image."""
        image = Image(content=b"not an image", content_type="image/jpeg")

        with pytest.raises(WikimediaPotdError):
            process_potd_image(image, max_dimension=200, webp_quality=75)

    def test_raises_when_decoded_size_exceeds_pixel_bound(self, mocker: MockerFixture) -> None:
        """Raises WikimediaPotdError when the decode would exceed MAX_DECODED_PIXELS."""
        mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.image_processing.MAX_DECODED_PIXELS",
            100,
        )

        with pytest.raises(WikimediaPotdError):
            process_potd_image(make_image(20, 20), max_dimension=200, webp_quality=75)

    def test_bound_applies_to_the_decoded_size_not_the_source_size(
        self, mocker: MockerFixture
    ) -> None:
        """Accepts an oversized JPEG that draft() decodes down under MAX_DECODED_PIXELS.

        A 1600x1600 source is over the bound below, but asking for a 200px longest edge lets
        the JPEG decoder run at 1/8 scale, so only 200x200 pixels are ever materialised.
        """
        mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.image_processing.MAX_DECODED_PIXELS",
            1_000_000,
        )

        result = process_potd_image(make_image(1600, 1600), max_dimension=200, webp_quality=75)

        with open_processed(result) as img:
            assert img.size == (200, 200)

    def test_bound_is_enforced_before_the_source_is_decoded(self, mocker: MockerFixture) -> None:
        """Rejects an oversized source without ever materialising its pixels.

        The bound exists to keep the job inside its pod memory limit, so it is worthless if
        the decode has already happened by the time it is checked.
        """
        mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.image_processing.MAX_DECODED_PIXELS",
            100,
        )
        # built before the spy so that encoding the source itself is not counted
        image = make_image(400, 400)
        load = mocker.spy(PILImage.Image, "load")

        with pytest.raises(WikimediaPotdError):
            process_potd_image(image, max_dimension=400, webp_quality=75)

        load.assert_not_called()
