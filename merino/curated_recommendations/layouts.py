"""The layouts below control how tiles are displayed in the sections experiment.

TODO: HNT-252 will document the QA process for layout changes. PR review suffices while we're in nightly.
"""

from merino.curated_recommendations.protocol import Layout, ResponsiveLayout, Tile, TileSize

# The following layouts are based on work-in-progress designs. The goal is to get some mock data to
# FE developers. Names and layouts will likely be changed.

# layout with 4 medium tiles, and an ad in 2nd position
layout_4_medium = Layout(
    name="4-medium-tiles-ad-position-1",
    responsiveLayouts=[
        ResponsiveLayout(
            columnCount=4,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True),
                Tile(size=TileSize.MEDIUM, position=2, hasAd=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=2,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True),
                Tile(size=TileSize.MEDIUM, position=2, hasAd=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=1,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True),
                Tile(size=TileSize.MEDIUM, position=2, hasAd=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=False),
            ],
        ),
    ],
)

# layout with 4 small tiles, and no ads
layout_4_small = Layout(
    name="4-small-tiles-no-ads",
    responsiveLayouts=[
        ResponsiveLayout(
            columnCount=4,
            tiles=[
                Tile(size=TileSize.SMALL, position=0, hasAd=False),
                Tile(size=TileSize.SMALL, position=1, hasAd=False),
                Tile(size=TileSize.SMALL, position=2, hasAd=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=2,
            tiles=[
                Tile(size=TileSize.SMALL, position=0, hasAd=False),
                Tile(size=TileSize.SMALL, position=1, hasAd=False),
                Tile(size=TileSize.SMALL, position=2, hasAd=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=1,
            tiles=[
                Tile(size=TileSize.SMALL, position=0, hasAd=False),
                Tile(size=TileSize.SMALL, position=1, hasAd=False),
                Tile(size=TileSize.SMALL, position=2, hasAd=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False),
            ],
        ),
    ],
)

# layout with large-medium-small tiles, and an ad in medium tile
layout_large_medium_small = Layout(
    name="1-large-2-small-1-medium-ad-position-3",
    responsiveLayouts=[
        ResponsiveLayout(
            columnCount=4,
            tiles=[
                Tile(size=TileSize.LARGE, position=0, hasAd=False),
                Tile(size=TileSize.SMALL, position=1, hasAd=False),
                Tile(size=TileSize.SMALL, position=2, hasAd=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=2,
            tiles=[
                Tile(size=TileSize.LARGE, position=0, hasAd=False),
                Tile(size=TileSize.SMALL, position=1, hasAd=False),
                Tile(size=TileSize.SMALL, position=2, hasAd=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=1,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False),
                Tile(size=TileSize.SMALL, position=3, hasAd=False),
            ],
        ),
    ],
)
