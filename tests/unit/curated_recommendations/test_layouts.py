"""Unit tests for section layouts, covering the invariants that the New Tab client relies on.

None of these are enforced by the Pydantic models, and breaking one degrades rendering rather
than raising, so they are asserted here for every layout in the module.
"""

import pytest

from merino.curated_recommendations.layouts import (
    layout_4_large,
    layout_4_medium,
    layout_6_tiles,
    layout_7_tiles_2_ads,
    layout_8_tiles_2_ads,
)
from merino.curated_recommendations.protocol import Layout, ResponsiveLayout, TileSize

ALL_LAYOUTS = [
    layout_4_medium,
    layout_4_large,
    layout_6_tiles,
    layout_7_tiles_2_ads,
    layout_8_tiles_2_ads,
]

# Grid footprint of each tile size as (rows, columns), in half-row units. Mirrors CARD_SIZE in
# CardSections.jsx, where a small is half the height of a medium and a large is twice its width.
TILE_FOOTPRINT: dict[TileSize, tuple[int, int]] = {
    TileSize.SMALL: (1, 1),
    TileSize.MEDIUM: (2, 1),
    TileSize.LARGE: (2, 2),
}


def place_tiles(responsive_layout: ResponsiveLayout) -> tuple[dict[tuple[int, int], int], int]:
    """Place tiles first-fit, as CSS grid auto-placement does.

    Returns a map of (row, column) to tile index, and the number of rows used.
    """
    columns = responsive_layout.columnCount
    occupied: dict[tuple[int, int], int] = {}
    max_row = 0

    for index, tile in enumerate(responsive_layout.tiles):
        rows, cols = TILE_FOOTPRINT[tile.size]
        # Every tile fits within twice the tile count in rows, so this bound is never hit.
        for row in range(2 * len(responsive_layout.tiles) + 2):
            for col in range(columns - cols + 1):
                cells = [(r, c) for r in range(row, row + rows) for c in range(col, col + cols)]
                if all(cell not in occupied for cell in cells):
                    occupied.update(dict.fromkeys(cells, index))
                    max_row = max(max_row, row + rows)
                    break
            else:
                continue
            break

    return occupied, max_row


def find_empty_cells(responsive_layout: ResponsiveLayout) -> list[tuple[int, int]]:
    """Return grid cells that no tile covers.

    An empty cell is a visible hole: either a partial final row, or the gap left by a small
    tile with no sibling stacked beneath it.
    """
    occupied, max_row = place_tiles(responsive_layout)
    return [
        (row, col)
        for row in range(max_row)
        for col in range(responsive_layout.columnCount)
        if (row, col) not in occupied
    ]


def first_row_tiles(responsive_layout: ResponsiveLayout) -> list[int]:
    """Return the indexes of tiles covering the top grid row, in column order."""
    occupied, _ = place_tiles(responsive_layout)
    indexes: list[int] = []
    for col in range(responsive_layout.columnCount):
        index = occupied.get((0, col))
        if index is not None and index not in indexes:
            indexes.append(index)
    return indexes


def ad_positions(responsive_layout: ResponsiveLayout) -> set[int]:
    """Return the content positions carrying an ad in this responsive layout."""
    return {tile.position for tile in responsive_layout.tiles if tile.hasAd}


@pytest.mark.parametrize("layout", ALL_LAYOUTS, ids=lambda layout: layout.name)
class TestLayoutInvariants:
    """Invariants that must hold for every layout Merino serves."""

    def test_every_row_is_full(self, layout: Layout) -> None:
        """No breakpoint leaves an empty grid cell.

        Firefox 154+ hides tiles in a partial final row; older clients render the hole. Either
        way the layout loses a tile, so layouts must fill their rows by construction.
        """
        empty = {
            responsive_layout.columnCount: find_empty_cells(responsive_layout)
            for responsive_layout in layout.responsiveLayouts
        }
        assert not any(empty.values()), f"{layout.name} has empty cells: {empty}"

    def test_tile_count_matches_across_breakpoints(self, layout: Layout) -> None:
        """Every breakpoint defines the same number of tiles.

        The client renders max(tiles) cards at every breakpoint and only styles a card when the
        active breakpoint defines a tile with its position, so a position that is missing from a
        narrower layout renders unstyled and visible.
        """
        counts = {
            responsive_layout.columnCount: len(responsive_layout.tiles)
            for responsive_layout in layout.responsiveLayouts
        }
        assert len(set(counts.values())) == 1, f"{layout.name} tile counts differ: {counts}"

    def test_responsive_layouts_are_ordered_widest_first(self, layout: Layout) -> None:
        """Responsive layouts are ordered 4 to 1 columns.

        DiscoveryStreamFeed sizes the ad request from responsiveLayouts[0], so the widest layout
        has to come first. The Layout validator only checks that all four are present.
        """
        column_counts = [
            responsive_layout.columnCount for responsive_layout in layout.responsiveLayouts
        ]
        assert column_counts == [4, 3, 2, 1], f"{layout.name} is ordered {column_counts}"

    def test_ad_count_matches_across_breakpoints(self, layout: Layout) -> None:
        """Every breakpoint defines the same number of ad tiles.

        The count of ads requested comes from the 4-column layout while their placement comes
        from the 1-column layout, so a mismatch either wastes a request or leaves a gap.
        """
        counts = {
            responsive_layout.columnCount: len(ad_positions(responsive_layout))
            for responsive_layout in layout.responsiveLayouts
        }
        assert len(set(counts.values())) == 1, f"{layout.name} ad counts differ: {counts}"


class TestLayout8Tiles2Ads:
    """Tests for the layout that replaces Popular Today's large tile (HNT-2920)."""

    def test_has_no_large_tiles(self) -> None:
        """No breakpoint uses a large tile, which is the point of the layout."""
        sizes = {
            tile.size
            for responsive_layout in layout_8_tiles_2_ads.responsiveLayouts
            for tile in responsive_layout.tiles
        }
        assert TileSize.LARGE not in sizes

    def test_has_eight_tiles_at_every_breakpoint(self) -> None:
        """Eight tiles is the smallest count above seven that fills rows without a large tile."""
        assert layout_8_tiles_2_ads.max_tile_count == 8
        for responsive_layout in layout_8_tiles_2_ads.responsiveLayouts:
            assert len(responsive_layout.tiles) == 8

    def test_ad_positions_match_across_breakpoints(self) -> None:
        """Ads sit at the same content positions everywhere.

        The client splices ads into the recommendation list using the 1-column positions only,
        so a breakpoint that flags different positions would mark a tile as an ad that receives
        an organic story instead.
        """
        for responsive_layout in layout_8_tiles_2_ads.responsiveLayouts:
            assert ad_positions(responsive_layout) == {1, 5}, (
                f"{responsive_layout.columnCount} columns has ads at "
                f"{ad_positions(responsive_layout)}"
            )

    def test_two_column_first_row_is_organic_then_ad(self) -> None:
        """At 2 columns the first row is an organic tile followed by an ad (HNT-2920 P0).

        This is the change being measured: previously a large tile filled the whole first row,
        so the 2-column layout showed no ad above the fold.
        """
        two_columns = next(
            responsive_layout
            for responsive_layout in layout_8_tiles_2_ads.responsiveLayouts
            if responsive_layout.columnCount == 2
        )
        first_row = two_columns.tiles[:2]
        assert [tile.position for tile in first_row] == [0, 1]
        assert [tile.hasAd for tile in first_row] == [False, True]
        assert all(tile.size is TileSize.MEDIUM for tile in first_row)

    def test_four_column_first_row_is_three_organic_then_ad(self) -> None:
        """At 4 columns the first row holds three organic tiles then the ad (HNT-2920 P1).

        The ad is at content position 1 so it agrees with the 1-column layout, but it is
        rendered last so it occupies the fourth column.
        """
        four_columns = next(
            responsive_layout
            for responsive_layout in layout_8_tiles_2_ads.responsiveLayouts
            if responsive_layout.columnCount == 4
        )
        first_row = four_columns.tiles[:4]
        assert [tile.hasAd for tile in first_row] == [False, False, False, True]
        assert first_row[-1].position == 1

    def test_first_row_tiles_have_no_excerpt(self) -> None:
        """First-row tiles drop the excerpt, replacing the large tile's excerpt treatment."""
        for responsive_layout in layout_8_tiles_2_ads.responsiveLayouts:
            for index in first_row_tiles(responsive_layout):
                tile = responsive_layout.tiles[index]
                assert not tile.hasExcerpt, (
                    f"{responsive_layout.columnCount} columns: position {tile.position} "
                    f"in the first row has an excerpt"
                )
