"""The layouts below control how tiles are displayed in the sections experiment.

When changing or adding a new layout, put the change behind a Nimbus experiment, such that
front-end engineering, product, and design can QA the layout before it reaches users.

Tile order should be based on horizontal stacking. You can try this out in the Mozilla Playground:
https://developer.mozilla.org/en-US/play?id=zWYUe3xC5v60fEuN8USHE24l7Q7tR2Vghi08O6KT9DAZz9cv%2B%2F0s0H8F7vJBWRVCnQgSHYWR%2BadDY4zA
"""

from merino.curated_recommendations.protocol import Layout, ResponsiveLayout, Tile, TileSize

# Layout 1: 4 medium tiles on 4 columns. Small tiles are used on fewer columns to display all items.
layout_4_medium = Layout(
    name="4-medium-small-1-ad",
    responsiveLayouts=[
        ResponsiveLayout(
            columnCount=4,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=2, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
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
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=3, hasAd=False, hasExcerpt=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=3,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=3, hasAd=False, hasExcerpt=False),
            ],
        ),
        ResponsiveLayout(
            columnCount=2,
            tiles=[
                Tile(size=TileSize.LARGE, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
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

# Layout 3: Layout with 6 tiles, ranging from small to medium.
layout_6_tiles = Layout(
    name="6-small-medium-1-ad",
    responsiveLayouts=[
        ResponsiveLayout(
            columnCount=4,
            tiles=[
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=3, hasAd=False, hasExcerpt=False),
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

# Layout 4: Layout with 7 tiles, intended to show the same number of ads as in the control branch.
layout_3_ads = Layout(
    name="7-double-row-3-ad",
    responsiveLayouts=[
        ResponsiveLayout(
            columnCount=4,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=2, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.LARGE, position=4, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=5, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=6, hasAd=False, hasExcerpt=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=3,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=6, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=4, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=5, hasAd=True, hasExcerpt=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=2,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=0, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=2, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.LARGE, position=4, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=5, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=6, hasAd=False, hasExcerpt=True),
            ],
        ),
        ResponsiveLayout(
            columnCount=1,
            tiles=[
                Tile(size=TileSize.MEDIUM, position=1, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.SMALL, position=0, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.SMALL, position=2, hasAd=False, hasExcerpt=False),
                Tile(size=TileSize.MEDIUM, position=3, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=4, hasAd=False, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=5, hasAd=True, hasExcerpt=True),
                Tile(size=TileSize.MEDIUM, position=6, hasAd=False, hasExcerpt=True),
            ],
        ),
    ],
)
