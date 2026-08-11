"""Unit tests for section layouts, covering the invariants that the New Tab client relies on.

None of these are enforced by the Pydantic models, and breaking one degrades or crashes
rendering rather than raising here, so they are asserted for every layout in the module.

The client rules modelled below, for reference:
  * Placement follows CSS `grid-auto-flow: row` (sparse): the cursor only moves forward, so a
    hole left behind it is never backfilled.
  * Tiles in a trailing incomplete row are hidden, so a layout may intentionally define more
    tiles than a breakpoint can show.
  * Visual order comes from the tiles array, not from `position`, which is an index into the
    list after ads have been spliced in.
"""

import pytest

from merino.curated_recommendations.layouts import (
    layout_4_large,
    layout_4_medium,
    layout_6_tiles,
    layout_7_tiles_2_ads,
    layout_8_tiles_2_ads,
)
from merino.curated_recommendations.protocol import Layout, ResponsiveLayout, Tile, TileSize

ALL_LAYOUTS = [
    layout_4_medium,
    layout_4_large,
    layout_6_tiles,
    layout_7_tiles_2_ads,
    layout_8_tiles_2_ads,
]


def footprint(size: TileSize, columns: int) -> tuple[int, int]:
    """Return the grid footprint (rows, columns) of a tile size at a breakpoint.

    A large spans two columns, except at one column where it is rendered as a medium.
    """
    if size is TileSize.SMALL:
        return 1, 1
    if size is TileSize.LARGE:
        return (2, 1) if columns == 1 else (2, 2)
    return 2, 1


def place_tiles(tiles: list[Tile], columns: int) -> tuple[dict[tuple[int, int], int], int]:
    """Place tiles as CSS `grid-auto-flow: row` does, with a cursor that only moves forward.

    Returns a map of (row, column) to tile index, and the number of rows used.
    """
    occupied: dict[tuple[int, int], int] = {}
    max_row, cursor_row, cursor_col = 0, 0, 0

    for index, tile in enumerate(tiles):
        rows, cols = footprint(tile.size, columns)
        row, col = cursor_row, cursor_col
        while True:
            if col + cols > columns:
                row, col = row + 1, 0
                continue
            cells = [(r, c) for r in range(row, row + rows) for c in range(col, col + cols)]
            if all(cell not in occupied for cell in cells):
                occupied.update(dict.fromkeys(cells, index))
                max_row = max(max_row, row + rows)
                cursor_row, cursor_col = row, col + cols
                break
            col += 1

    return occupied, max_row


def find_empty_cells(tiles: list[Tile], columns: int) -> list[tuple[int, int]]:
    """Return grid cells that no tile covers."""
    occupied, max_row = place_tiles(tiles, columns)
    return [
        (row, col)
        for row in range(max_row)
        for col in range(columns)
        if (row, col) not in occupied
    ]


def hidden_tiles(tiles: list[Tile], columns: int) -> set[int]:
    """Return the indexes of tiles in a trailing incomplete row, which the client hides.

    Ported from getOrphanTileIndexes. Widths are in half-columns so that a small, which is
    half the height of a medium, can be accounted for as it stacks.
    """
    span = {TileSize.SMALL: (2, 1), TileSize.MEDIUM: (2, 2), TileSize.LARGE: (4, 2)}
    row_width = columns * 2
    current: list[int] = []
    filled = carry = 0

    for index, tile in enumerate(tiles):
        width, height = span[tile.size]
        current.append(index)
        filled += width
        if height > 1:
            carry += width
        if filled >= row_width:
            current, filled, carry = [], carry, 0
            if filled >= row_width:
                filled = 0

    return set(current)


def visible_tiles(responsive_layout: ResponsiveLayout) -> list[Tile]:
    """Return the tiles a user actually sees at this breakpoint."""
    hidden = hidden_tiles(responsive_layout.tiles, responsive_layout.columnCount)
    return [tile for index, tile in enumerate(responsive_layout.tiles) if index not in hidden]


def ad_positions(responsive_layout: ResponsiveLayout) -> set[int]:
    """Return the content positions carrying an ad in this responsive layout."""
    return {tile.position for tile in responsive_layout.tiles if tile.hasAd}


def responsive(layout: Layout, columns: int) -> ResponsiveLayout:
    """Return a layout's responsive layout for a given column count."""
    return next(
        responsive_layout
        for responsive_layout in layout.responsiveLayouts
        if responsive_layout.columnCount == columns
    )


def ad_cells(layout: Layout, columns: int) -> set[tuple[int, int]]:
    """Return the grid cells the ad tiles occupy at a breakpoint."""
    responsive_layout = responsive(layout, columns)
    occupied, _ = place_tiles(responsive_layout.tiles, columns)
    return {
        cell
        for cell, index in occupied.items()
        if responsive_layout.tiles[index].hasAd
    }


@pytest.mark.parametrize("layout", ALL_LAYOUTS, ids=lambda layout: layout.name)
class TestLayoutInvariants:
    """Invariants that must hold for every layout Merino serves."""

    def test_visible_grid_has_no_holes(self, layout: Layout) -> None:
        """What the user sees fills its rows at every breakpoint.

        A trailing incomplete row is fine because the client hides it. A hole *behind* the
        placement cursor is not: nothing cleans it up, because sparse auto-placement never
        backfills. The commonest cause is a small tile with no sibling stacked beneath it.
        """
        empty = {
            responsive_layout.columnCount: find_empty_cells(
                visible_tiles(responsive_layout), responsive_layout.columnCount
            )
            for responsive_layout in layout.responsiveLayouts
        }
        assert not any(empty.values()), f"{layout.name} has holes when rendered: {empty}"

    def test_tile_count_matches_across_breakpoints(self, layout: Layout) -> None:
        """Every breakpoint defines the same number of tiles.

        The client renders max(tiles) cards and looks up each card's image size by the active
        breakpoint. A position defined at one breakpoint but missing at another dereferences
        an undefined entry and throws, taking out the section.
        """
        counts = {
            responsive_layout.columnCount: len(responsive_layout.tiles)
            for responsive_layout in layout.responsiveLayouts
        }
        assert len(set(counts.values())) == 1, f"{layout.name} tile counts differ: {counts}"

    def test_position_sets_match_across_breakpoints(self, layout: Layout) -> None:
        """Every breakpoint defines the same set of positions, for the same reason."""
        position_sets = {
            responsive_layout.columnCount: frozenset(
                tile.position for tile in responsive_layout.tiles
            )
            for responsive_layout in layout.responsiveLayouts
        }
        assert len(set(position_sets.values())) == 1, f"{layout.name}: {position_sets}"

    def test_responsive_layouts_are_ordered_widest_first(self, layout: Layout) -> None:
        """Responsive layouts are ordered 4 to 1 columns.

        The ad request reads responsiveLayouts[0] by array index, so the widest layout has to
        come first. The Layout validator only checks that all four are present.
        """
        column_counts = [
            responsive_layout.columnCount for responsive_layout in layout.responsiveLayouts
        ]
        assert column_counts == [4, 3, 2, 1], f"{layout.name} is ordered {column_counts}"

    def test_ad_positions_match_across_breakpoints(self, layout: Layout) -> None:
        """Every breakpoint flags the same positions as ads.

        Ads are spliced into the recommendation list using the 1-column positions only, so a
        breakpoint that flags a different position marks a tile as an ad while it actually
        receives an organic story, and leaves the real ad tile unflagged.
        """
        flagged = {
            responsive_layout.columnCount: frozenset(ad_positions(responsive_layout))
            for responsive_layout in layout.responsiveLayouts
        }
        assert len(set(flagged.values())) == 1, f"{layout.name} ad positions differ: {flagged}"


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
        """Eight tiles fill both rows at 4 columns, which seven cannot without a large tile."""
        assert layout_8_tiles_2_ads.max_tile_count == 8
        for responsive_layout in layout_8_tiles_2_ads.responsiveLayouts:
            assert len(responsive_layout.tiles) == 8

    def test_ad_positions_match_across_breakpoints(self) -> None:
        """Ads sit at the same content positions everywhere.

        Ads are spliced into the recommendation list using the 1-column positions only, so a
        breakpoint flagging different positions would mark a tile as an ad that receives an
        organic story instead.
        """
        for responsive_layout in layout_8_tiles_2_ads.responsiveLayouts:
            assert ad_positions(responsive_layout) == {1, 5}, (
                f"{responsive_layout.columnCount} columns has ads at "
                f"{ad_positions(responsive_layout)}"
            )

    def test_every_ad_is_visible(self) -> None:
        """No ad tile falls into the hidden trailing row at any breakpoint."""
        for responsive_layout in layout_8_tiles_2_ads.responsiveLayouts:
            visible = {tile.position for tile in visible_tiles(responsive_layout) if tile.hasAd}
            assert visible == {1, 5}, (
                f"{responsive_layout.columnCount} columns only shows ads at {visible}"
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

    def test_three_columns_renders_exactly_what_it_does_today(self) -> None:
        """At 3 columns the visible tiles are identical to the layout being replaced.

        There is no large tile at this breakpoint, so nothing should change for these users.
        The eighth tile exists only to keep the position set consistent across breakpoints,
        and lands in a trailing row on its own, which the client hides.
        """
        new_layout = responsive(layout_8_tiles_2_ads, 3)
        assert visible_tiles(new_layout) == responsive(layout_7_tiles_2_ads, 3).tiles
        assert len(hidden_tiles(new_layout.tiles, 3)) == 1

    def test_ads_keep_the_cells_they_occupy_today(self) -> None:
        """Neither ad moves at 4 or 3 columns, so the experiment isolates the large tile.

        At 2 columns the row-1 ad moves by design: that is the change being measured.
        """
        for columns in (4, 3):
            assert ad_cells(layout_8_tiles_2_ads, columns) == ad_cells(
                layout_7_tiles_2_ads, columns
            ), f"an ad moved at {columns} columns"
