"""The layouts below control how tiles are displayed in the sections experiment.

TODO: HNT-252 will document the QA process for layout changes. PR review suffices while we're in nightly.
"""

from merino.curated_recommendations.protocol import Layout, ResponsiveLayout, Tile, TileSize

# The following layouts are based on work-in-progress designs. The goal is to get some mock data to
# FE developers. Names and layouts will likely be changed.

# Layout 1: 4 medium tiles on 4 columns. Small tiles are used on fewer columns to display all items.
layout_4_medium = Layout(
    name="4-medium-small-1-ad",
    responsiveLayouts=[
        ResponsiveLayout(
            columnCount=4,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=2, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=False, hasExcerpt=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=3,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False, hasExcerpt=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=2,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False, hasExcerpt=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=1,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False, hasExcerpt=False),
            ],
        ),
    ],
)

# Layout 2: Lead with a large tile.
layout_4_large = Layout(
    name="4-large-small-medium-1-ad",
    responsiveLayouts=[
        ResponsiveLayout(
            columnCount=4,
            tiles=[
                Tile(size=TileSize.LARGE, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=1, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=3,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=1, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=2,
            tiles=[
                Tile(size=TileSize.LARGE, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=1, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=1,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False, hasExcerpt=False),
            ],
        ),
    ],
)

# Layout 3: Layout with 6 tiles, ranging from small to medium.
layout_6_tiles = Layout(
    name="6-small-medium-1-ad",
    responsiveLayouts=[
        ResponsiveLayout(
            columnCount=4,
            tiles=[
                Tile(size=TileSize.SMALL, position=0, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=1, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=2, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=4, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=5, hasAd=False, hasExcerpt=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=3,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=2, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=4, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=5, hasAd=False, hasExcerpt=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=2,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=4, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=5, hasAd=False, hasExcerpt=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=1,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=4, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=5, hasAd=False, hasExcerpt=False),
            ],
        ),
    ],
)
