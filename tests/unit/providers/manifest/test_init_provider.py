# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the __init__ manifest provider module."""

from unittest.mock import patch
import pytest

from merino.providers.manifest import get_provider, init_provider
from merino.providers.manifest.provider import Provider as ManifestProvider


@pytest.mark.asyncio
async def test_init_provider() -> None:
    """Test for the `init_provider` method of the manifest provider"""
    await init_provider()

    from merino.providers.manifest import provider

    assert provider is not None
    assert isinstance(provider, ManifestProvider)
    assert provider.name == "manifest"


def test_get_provider_not_initialized() -> None:
    """Verify that get_provider raises ValueError when provider is not initialized."""
    with patch("merino.providers.manifest.provider", None):
        with pytest.raises(ValueError, match="Manifest provider has not been initialized."):
            get_provider()
