"""This module contains pytest unit tests for the Layout, ResponsiveLayout, and Tile models."""

import pytest
from pydantic import ValidationError

from merino.curated_recommendations.protocol import Layout, ResponsiveLayout, Tile, TileSize


@pytest.fixture
def valid_tile():
    """Fixture returning a helper to create a valid Tile instance."""

    def _create_tile(
        position: int,
        size: TileSize = TileSize.MEDIUM,
        hasAd: bool = False,
        hasExcerpt: bool = True,
    ):
        return Tile(size=size, position=position, hasAd=hasAd, hasExcerpt=hasExcerpt)

    return _create_tile


@pytest.fixture
def responsive_layout(valid_tile):
    """Fixture returning a helper to create a valid ResponsiveLayout with a given columnCount and tile count."""

    def _create_layout(columnCount: int, tile_count: int) -> ResponsiveLayout:
        tiles = [valid_tile(position=i) for i in range(tile_count)]
        return ResponsiveLayout(columnCount=columnCount, tiles=tiles)

    return _create_layout


@pytest.fixture
def valid_layout(responsive_layout):
    """Fixture that returns a valid Layout instance with responsive layouts for column counts 1, 2, 3, and 4."""
    responsive_layouts = [
        responsive_layout(1, 3),
        responsive_layout(2, 4),
        responsive_layout(3, 5),
        responsive_layout(4, 2),
    ]
    return Layout(name="Valid Layout", responsiveLayouts=responsive_layouts)


class TestTile:
    """Tests for Tile validations."""

    @pytest.mark.parametrize(
        "size, hasAd",
        [
            (TileSize.SMALL, True),
            (TileSize.LARGE, True),
        ],
    )
    def test_no_ad_on_small_or_large_tiles_failure(self, valid_tile, size, hasAd):
        """Test that Tile creation fails when a SMALL or LARGE tile is created with hasAd True."""
        # For SMALL tiles, hasExcerpt must be False; for LARGE tiles, we'll use a valid hasExcerpt value (True)
        hasExcerpt = False if size == TileSize.SMALL else True
        with pytest.raises(ValidationError):
            valid_tile(0, size=size, hasAd=hasAd, hasExcerpt=hasExcerpt)


class TestResponsiveLayout:
    """Tests for ResponsiveLayout validations."""

    @pytest.mark.parametrize("column_count", [0, 5])
    def test_validate_column_count(self, column_count):
        """Test that ResponsiveLayout creation fails when columnCount is outside the valid range (1-4)."""
        with pytest.raises(ValidationError):
            ResponsiveLayout(columnCount=column_count, tiles=[])

    def test_validate_tile_positions_failure(self, valid_tile):
        """Test that ResponsiveLayout creation fails when tile positions are not contiguous from 0 to n-1."""
        # Create tiles with positions [0, 1, 3] (missing 2)
        tiles = [valid_tile(0), valid_tile(1), valid_tile(3)]
        with pytest.raises(ValidationError):
            ResponsiveLayout(columnCount=3, tiles=tiles)

    def test_validate_tile_positions_0_indexed(self, valid_tile):
        """Test that ResponsiveLayout creation fails when tile positions are 0-indexed."""
        # Create tiles with positions [1, 2, 3] (missing 0)
        tiles = [valid_tile(1), valid_tile(2), valid_tile(3)]
        with pytest.raises(ValidationError):
            ResponsiveLayout(columnCount=3, tiles=tiles)


class TestLayout:
    """Tests for Layout validations and properties."""

    def test_max_tile_count(self, valid_layout):
        """Test that the max_tile_count property returns the maximum number of tiles in any responsive layout."""
        assert valid_layout.max_tile_count == 5

    @pytest.mark.parametrize(
        "invalid_responsive_layouts",
        [
            # Missing one column count (only 1, 2, 3)
            [
                ResponsiveLayout(columnCount=1, tiles=[]),
                ResponsiveLayout(columnCount=2, tiles=[]),
                ResponsiveLayout(columnCount=3, tiles=[]),
            ],
            # Duplicate column counts (two layouts for column count 1)
            [
                ResponsiveLayout(columnCount=1, tiles=[]),
                ResponsiveLayout(columnCount=1, tiles=[]),
                ResponsiveLayout(columnCount=2, tiles=[]),
                ResponsiveLayout(columnCount=3, tiles=[]),
            ],
        ],
    )
    def test_must_include_all_column_counts_failure(self, invalid_responsive_layouts):
        """Test that Layout creation fails when responsiveLayouts do not include exactly one layout for column counts 1–4."""
        with pytest.raises(ValidationError):
            Layout(name="Invalid Layout", responsiveLayouts=invalid_responsive_layouts)
