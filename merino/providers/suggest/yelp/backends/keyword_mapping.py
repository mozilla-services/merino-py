"""Module containing keywords for yelp."""

CATEGORIES: frozenset[str] = frozenset(
    {
        "coffeeshops",
        "gelato",
        "ice cream & frozen yogurt",
        "pancakes",
        "ramen",
    }
)
LOCATION_KEYWORDS: frozenset[str] = frozenset(
    {"around me", "in area", "near by", "near me", "nearby"}
)
