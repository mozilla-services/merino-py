# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Widgets Manifest module."""

from unittest.mock import patch

from merino.providers.widgets.iframed.backends.widgets_manifest import build_manifest


def test_build_manifest_happy_path() -> None:
    """Test happy path."""
    with (
        patch(
            "merino.providers.widgets.iframed.backends.widgets_manifest.settings"
        ) as mock_settings,
    ):
        mock_settings.widgets.providers.framed.bucket_name_kayak_travel = "test"
        mock_settings.widgets.providers.framed.bucket_name_wrexhamafc = "test"
        mock_settings.widgets.providers.framed.bucket_name_yahoo_horoscope = "test"
        mock_settings.widgets.providers.framed.bucket_name_yahoo_solitaire = "test"
        mock_settings.widgets.providers.framed.cdn_hostname_kayak_travel = "test"
        mock_settings.widgets.providers.framed.cdn_hostname_wrexhamafc = "test"
        mock_settings.widgets.providers.framed.cdn_hostname_yahoo_horoscope = "test"
        mock_settings.widgets.providers.framed.cdn_hostname_yahoo_solitaire = "test"

        widgets = build_manifest()

        assert len(widgets) == 4


def test_build_manifest_missing_values() -> None:
    """Test missing settings values remove widgets from manifest."""
    with (
        patch(
            "merino.providers.widgets.iframed.backends.widgets_manifest.settings"
        ) as mock_settings,
    ):
        # yahoo horoscope and solitaire should not be included as required
        # values are empty
        mock_settings.widgets.providers.framed.bucket_name_kayak_travel = "test"
        mock_settings.widgets.providers.framed.bucket_name_wrexhamafc = "test"
        mock_settings.widgets.providers.framed.bucket_name_yahoo_horoscope = ""
        mock_settings.widgets.providers.framed.bucket_name_yahoo_solitaire = "test"
        mock_settings.widgets.providers.framed.cdn_hostname_kayak_travel = "test"
        mock_settings.widgets.providers.framed.cdn_hostname_wrexhamafc = "test"
        mock_settings.widgets.providers.framed.cdn_hostname_yahoo_horoscope = "test"
        mock_settings.widgets.providers.framed.cdn_hostname_yahoo_solitaire = ""

        widgets = build_manifest()

        assert len(widgets) == 2
