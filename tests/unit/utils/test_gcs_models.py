# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the GCS models module."""

import io
import pytest
from PIL import Image as PILImage
from merino.utils.gcs.models import Image, BaseContentUploader


def create_test_image_bytes(mode="RGB", size=(100, 100), color=(255, 0, 0)):
    """Create a test image."""
    with io.BytesIO() as output:
        img = PILImage.new(mode, size, color)
        img.save(output, format="PNG")
        return output.getvalue()


def test_image_open_and_get_dimensions():
    """Test image open and get dimensions."""
    # Create test image bytes (a red 100x100 PNG)
    image_bytes = create_test_image_bytes(size=(100, 100))
    # Construct an instance of our Image model (from gcs/models.py)
    test_image = Image(content=image_bytes, content_type="image/png")

    # Test that open() returns a PIL Image with the expected dimensions
    pil_image = test_image.open()
    assert isinstance(pil_image, PILImage.Image)
    assert pil_image.size == (100, 100)

    # Test get_dimensions() returns the correct tuple
    dimensions = test_image.get_dimensions()
    assert dimensions == (100, 100)


def test_image_open_invalid_bytes():
    """Test image open with invalid bytes."""
    # Provide data that is not a valid image
    invalid_bytes = b"this is not an image"
    test_image = Image(content=invalid_bytes, content_type="image/png")
    with pytest.raises(Exception):  # PIL is expected to raise an exception (e.g. OSError)
        test_image.open()


class DummyBlob:
    """Dummy blob."""

    # A simple dummy blob with only a public_url attribute.
    def __init__(self, destination_name: str):
        self.public_url = f"http://dummy/{destination_name}"


class DummyUploader(BaseContentUploader):
    """Dummy uploader."""

    def upload_content(
        self, content, destination_name, content_type="text/plain", forced_upload=False
    ) -> DummyBlob:
        """Upload dummy content."""
        # Return a dummy blob with a predictable URL
        return DummyBlob(destination_name)

    def upload_image(self, image: Image, destination_name: str, forced_upload=None) -> str:
        """Upload dummy image."""
        # Use upload_content to simulate uploading and get the URL
        blob = self.upload_content(
            image.content, destination_name, image.content_type, forced_upload
        )
        return blob.public_url

    def get_most_recent_file(
        self, match: str, sort_key, exclusion: str | None
    ) -> DummyBlob | None:
        """Get most recent file."""
        # For the purpose of testing, return a dummy blob if exclusion is non-empty; otherwise, return None.
        if exclusion:
            return DummyBlob("recent_file")
        return None


def test_dummy_uploader_upload_content():
    """Test dummy uploader upload content."""
    uploader = DummyUploader()
    content = "sample text"
    destination = "file.txt"
    blob = uploader.upload_content(content, destination, content_type="text/plain")
    # Verify that the dummy blob returns the expected public URL
    assert hasattr(blob, "public_url")
    assert blob.public_url == f"http://dummy/{destination}"


def test_dummy_uploader_upload_image():
    """Test dummy uploader upload image."""
    # Create a simple test image
    image_bytes = create_test_image_bytes(size=(50, 50))
    test_image = Image(content=image_bytes, content_type="image/png")
    uploader = DummyUploader()
    destination = "test_image.png"
    url = uploader.upload_image(test_image, destination)
    # Check that the URL is as expected
    assert url == f"http://dummy/{destination}"


def test_dummy_uploader_get_most_recent_file():
    """Test dummy uploader get most recent file."""
    uploader = DummyUploader()
    # Test that when exclusion is provided the uploader returns a DummyBlob
    blob = uploader.get_most_recent_file("match", sort_key=lambda x: x, exclusion="exclude.txt")
    assert blob is not None
    assert blob.public_url == "http://dummy/recent_file"
    # Test that when exclusion is empty the uploader returns None
    blob_none = uploader.get_most_recent_file("match", exclusion="", sort_key=lambda x: x)
    assert blob_none is None
