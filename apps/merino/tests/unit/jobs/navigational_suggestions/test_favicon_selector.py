# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for favicon_selector module."""

from merino.jobs.navigational_suggestions.favicon.favicon_selector import FaviconSelector


class TestIsBetterFavicon:
    """Tests for FaviconSelector.is_better_favicon method."""

    def test_prefers_higher_priority_source(self):
        """Test that link source (priority 1) is preferred over meta (priority 2)."""
        favicon = {"_source": "link"}
        result = FaviconSelector.is_better_favicon(favicon, 100, 100, "meta")
        assert result is True

    def test_rejects_lower_priority_source(self):
        """Test that meta source is not preferred over link."""
        favicon = {"_source": "meta"}
        result = FaviconSelector.is_better_favicon(favicon, 100, 100, "link")
        assert result is False

    def test_prefers_larger_size_same_priority(self):
        """Test that larger size is preferred when source priority is the same."""
        favicon = {"_source": "link"}
        result = FaviconSelector.is_better_favicon(favicon, 200, 100, "link")
        assert result is True

    def test_rejects_smaller_size_same_priority(self):
        """Test that smaller size is rejected when source priority is the same."""
        favicon = {"_source": "link"}
        result = FaviconSelector.is_better_favicon(favicon, 100, 200, "link")
        assert result is False

    def test_rejects_equal_size_same_priority(self):
        """Test that equal size is not considered better."""
        favicon = {"_source": "link"}
        result = FaviconSelector.is_better_favicon(favicon, 100, 100, "link")
        assert result is False

    def test_handles_missing_source(self):
        """Test handling of favicon without _source field (defaults to 'default')."""
        favicon = {}
        result = FaviconSelector.is_better_favicon(favicon, 100, 100, "link")
        assert result is False

    def test_handles_unknown_source(self):
        """Test handling of unknown source type (gets default priority 4)."""
        favicon = {"_source": "unknown"}
        result = FaviconSelector.is_better_favicon(favicon, 100, 100, "link")
        assert result is False

    def test_source_priority_order(self):
        """Test the complete source priority order: link < meta < manifest < default."""
        # link (1) beats meta (2)
        assert FaviconSelector.is_better_favicon({"_source": "link"}, 100, 100, "meta") is True
        # meta (2) beats manifest (3)
        assert FaviconSelector.is_better_favicon({"_source": "meta"}, 100, 100, "manifest") is True
        # manifest (3) beats default (4)
        assert (
            FaviconSelector.is_better_favicon({"_source": "manifest"}, 100, 100, "default") is True
        )


class TestSelectBestFavicon:
    """Tests for FaviconSelector.select_best_favicon method."""

    def test_selects_favicon_with_highest_priority_source(self):
        """Test selection of favicon from highest priority source."""
        favicons = [
            {"url": "manifest.png", "_source": "manifest"},
            {"url": "link.ico", "_source": "link"},
            {"url": "meta.png", "_source": "meta"},
        ]
        dimensions = [(100, 100), (100, 100), (100, 100)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions)

        assert best is not None
        assert best["_source"] == "link"
        assert width == 100

    def test_selects_larger_favicon_same_source(self):
        """Test selection of larger favicon when source priority is the same."""
        favicons = [
            {"url": "small.ico", "_source": "link"},
            {"url": "large.ico", "_source": "link"},
            {"url": "medium.ico", "_source": "link"},
        ]
        dimensions = [(50, 50), (200, 200), (100, 100)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions)

        assert best is not None
        assert best["url"] == "large.ico"
        assert width == 200

    def test_uses_minimum_dimension_for_non_square(self):
        """Test that minimum of width and height is used for non-square images."""
        favicons = [
            {"url": "wide.png", "_source": "link"},
            {"url": "tall.png", "_source": "link"},
        ]
        dimensions = [(200, 50), (50, 200)]  # Both have min dimension of 50

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions)

        assert best is not None
        assert width == 50  # Uses minimum dimension

    def test_respects_minimum_width_requirement(self):
        """Test that favicons below minimum width are rejected."""
        favicons = [
            {"url": "small.ico", "_source": "link"},
        ]
        dimensions = [(50, 50)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions, min_width=100)

        assert best is None
        assert width == 0

    def test_accepts_favicon_meeting_minimum_width(self):
        """Test that favicons meeting minimum width are accepted."""
        favicons = [
            {"url": "large.ico", "_source": "link"},
        ]
        dimensions = [(150, 150)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions, min_width=100)

        assert best is not None
        assert best["url"] == "large.ico"
        assert width == 150

    def test_selects_best_above_minimum(self):
        """Test selection of best favicon when multiple meet minimum."""
        favicons = [
            {"url": "medium.ico", "_source": "meta"},
            {"url": "large.ico", "_source": "link"},
            {"url": "small.ico", "_source": "link"},
        ]
        dimensions = [(150, 150), (200, 200), (100, 100)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions, min_width=50)

        assert best is not None
        assert best["url"] == "large.ico"  # Best is link source with largest size
        assert width == 200

    def test_returns_none_for_empty_list(self):
        """Test that None is returned for empty favicon list."""
        best, width = FaviconSelector.select_best_favicon([], [])

        assert best is None
        assert width == 0

    def test_returns_none_for_mismatched_lengths(self):
        """Test that None is returned when favicons and dimensions lists don't match."""
        favicons = [{"url": "icon.ico", "_source": "link"}]
        dimensions = [(100, 100), (200, 200)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions)

        assert best is None
        assert width == 0

    def test_handles_favicons_without_source_field(self):
        """Test handling of favicons without _source field."""
        favicons = [
            {"url": "no-source.ico"},  # No _source field
            {"url": "with-source.ico", "_source": "link"},
        ]
        dimensions = [(100, 100), (100, 100)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions)

        assert best is not None
        assert best["url"] == "with-source.ico"  # Link source wins over default

    def test_zero_minimum_width_accepts_all(self):
        """Test that min_width=0 accepts all favicons."""
        favicons = [
            {"url": "tiny.ico", "_source": "link"},
        ]
        dimensions = [(1, 1)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions, min_width=0)

        assert best is not None
        assert width == 1

    def test_complex_selection_scenario(self):
        """Test complex scenario with multiple sources and sizes."""
        favicons = [
            {"url": "default-small.ico", "_source": "default"},
            {"url": "manifest-large.png", "_source": "manifest"},
            {"url": "meta-medium.png", "_source": "meta"},
            {"url": "link-small.ico", "_source": "link"},
            {"url": "link-large.ico", "_source": "link"},
        ]
        dimensions = [(50, 50), (300, 300), (150, 150), (50, 50), (250, 250)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions, min_width=100)

        # Should select the largest link source that meets minimum width
        assert best is not None
        assert best["url"] == "link-large.ico"
        assert best["_source"] == "link"
        assert width == 250

    def test_handles_non_square_with_minimum_width(self):
        """Test non-square images with minimum width requirement."""
        favicons = [
            {"url": "wide.png", "_source": "link"},  # 300x50, min=50
            {"url": "tall.png", "_source": "link"},  # 50x300, min=50
            {"url": "square.png", "_source": "link"},  # 100x100, min=100
        ]
        dimensions = [(300, 50), (50, 300), (100, 100)]

        best, width = FaviconSelector.select_best_favicon(favicons, dimensions, min_width=75)

        # Only square.png meets the minimum width requirement (min dimension >= 75)
        assert best is not None
        assert best["url"] == "square.png"
        assert width == 100
