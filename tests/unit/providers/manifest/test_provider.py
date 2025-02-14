# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the manifest provider module."""

from unittest.mock import patch
import pytest

from merino.providers.manifest.backends.protocol import (
    GetManifestResultCode,
    ManifestBackendError,
    ManifestData,
)
from merino.providers.manifest.provider import Provider
from merino.providers.manifest.backends.manifest import ManifestBackend


@pytest.mark.asyncio
async def test_initialize(
    manifest_provider: Provider, backend: ManifestBackend, manifest_data: ManifestData, cleanup
) -> None:
    """Test initialization of manifest provider"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        result_code, _ = await backend.fetch()

        assert result_code is GetManifestResultCode.SUCCESS
        assert manifest_provider.manifest_data == manifest_data
        assert manifest_provider.last_fetch_at > 0

# TODO REFACTOR THIS
@pytest.mark.asyncio
async def test_get_manifest_data(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
) -> None:
    """Test get_manifest_data method returns manifest data"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        result = manifest_provider.get_manifest_data()
        assert result is not None
        assert result == manifest_provider.manifest_data
        assert manifest_provider.manifest_data == manifest_data


# @pytest.mark.asyncio
# async def test_get_manifest_data_empty_data(manifest_provider: Provider, cleanup) -> None:
#     """Test get_manifest_data method returns empty manifest data object if backend returns SKIP"""
#     with patch(
#         "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
#         return_value=(GetManifestResultCode.SKIP, None),
#     ):
#         await manifest_provider.initialize()
#         await cleanup(manifest_provider)

#         manifest_data = manifest_provider.get_manifest_data()

#         assert manifest_data is not None
#         assert manifest_data.domains == []


@pytest.mark.asyncio
async def test_should_fetch_true(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
) -> None:
    """Test should_fetch method returns true based on the resync interval"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        # difference between last fetch and current time is 100000 (greater than 86400)
        with patch(
            "merino.providers.manifest.provider.time.time", side_effect=[100000, 200000, 300000]
        ):
            await manifest_provider.initialize()
            await cleanup(manifest_provider)

            should_fetch = manifest_provider._should_fetch()

            assert should_fetch is True


@pytest.mark.asyncio
async def test_should_fetch_false(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
) -> None:
    """Test should_fetch method returns false based on the resync interval"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        # difference between last fetch and current time is 40000 (less than 86400)
        with patch(
            "merino.providers.manifest.provider.time.time", side_effect=[100000, 140000, 200000]
        ):
            await manifest_provider.initialize()
            await cleanup(manifest_provider)

            should_fetch = manifest_provider._should_fetch()

            assert should_fetch is False


@pytest.mark.asyncio
async def test_fetch_data_success(
    manifest_provider: Provider, manifest_data: ManifestData, cleanup
) -> None:
    """Test fetch_data method sets manifest data on SUCCESS"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.SUCCESS, manifest_data),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        await manifest_provider._fetch_data()

        assert manifest_provider.manifest_data is not None
        assert manifest_provider.manifest_data == manifest_data


# @pytest.mark.asyncio
# async def test_fetch_data_skip(manifest_provider: Provider, cleanup) -> None:
#     """Test fetch_data method does not set manifest data on SKIP"""
#     with patch(
#         "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
#         return_value=(GetManifestResultCode.SKIP, None),
#     ):
#         await manifest_provider.initialize()
#         await cleanup(manifest_provider)

#         await manifest_provider._fetch_data()

#         # manifest data remains empty ManifestData instance after initialization
#         assert manifest_provider.manifest_data is not None
#         assert manifest_provider.manifest_data.domains == []


@pytest.mark.asyncio
async def test_fetch_data_fail(manifest_provider: Provider, cleanup) -> None:
    """Test fetch_data method does not set manifest data when a failure occurs"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        return_value=(GetManifestResultCode.FAIL, None),
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        await manifest_provider._fetch_data()

        # manifest data remains empty ManifestData instance after initialization
        assert manifest_provider.manifest_data is not None
        assert manifest_provider.manifest_data.domains == []


@pytest.mark.asyncio
async def test_fetch_data_error(manifest_provider: Provider, cleanup) -> None:
    """Test fetch_data method does not set manifest data when an error occurs"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestBackend.fetch",
        side_effect=ManifestBackendError,
    ):
        await manifest_provider.initialize()
        await cleanup(manifest_provider)

        await manifest_provider._fetch_data()

        # manifest data remains empty ManifestData instance after initialization
        assert manifest_provider.manifest_data is not None
        assert manifest_provider.manifest_data.domains == []
