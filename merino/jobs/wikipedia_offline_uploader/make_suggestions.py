"""Generate Firefox Suggest suggestions based on the Wikipedia top viewed pages.

Usage:

    # Generate 7000 Wikipedia suggestions based on frequency or recency.

Note:
    * The keywords are generated based on the title field of the input. All `_`s
      are replaced with whitespaces and then lowercased before processing.
      Other punctuations (`,`, `.`, `:` etc.) are left untouched
    * The minimal keyword size is controlled by `MIN_KEYWORD_LEN`, which is set
      to `2` to match the minimal suggestion trigger threshold in Firefox
    * Various leading words are skipped in keywords generating:
        * `the`, `an`, and `a`
        * leading numerics such as `2022`
    * Each keyword is only associated with one suggestion. Keywords are assigned
      to suggestions in an FIFO manner based on the order (frequency or recency)
      of the associated Wikipedia page
    * Each suggestion should have at least `MIN_KEYWORDS` keywords, otherwise
      that suggestion will be excluded in the output. To produce the expected
      amount suggestions, it's a good idea to provide a little more (+10%) than
      expected in the upstream producers (i.e. top_n_by_frequency or top_n_by_recency)
    * To avoid having excessive keyword list for long titles, the total number of
      keywords for each suggestion is capped by `MAX_KEYWORDS`
    * Suggestion `id` is hardcoded to `0` for now. We might assign a valid ID to
      each suggestion later if needed
    * Suggestion `icon` is also hardcoded to `ICON_ID`, which is already uploaded
      to Remote Settings
    * The path of the suggestion URL is escaped (quoted) so that it's safe to
      use and store
"""

import re
from itertools import filterfalse, islice, takewhile
from typing import List, Pattern, Set, Generator, Any
from urllib.parse import quote

# Max # of keywords for each suggestion.
MAX_KEYWORDS = 25

# Min # of keywords for each suggestion. We should *not* provide a suggestion
# if its available keywords are fewer than this threshold.
MIN_KEYWORDS = 3

# Minimal keyword length
MIN_KEYWORD_LEN = 2

# URL prefix for Wikipedia
URL_PREFIX = "https://{language}.wikipedia.org/wiki/"

# Prefix of the output file
OUTPUT_PREFIX = "./rs-data/data-wikipedia"

# The hardcoded icon ID on Remote Settings
ICON_ID = "161351842074695"

# Max # of suggestions for a Remote Settings attachment
RS_CHUNK_SIZE = 200

# A set to store all the keywords observed thus far.
SEEN_KEYWORDS: Set[str] = set([])

# The leading words to be skipped
SKIP_WORDS: Pattern = re.compile(r"(\d+|the|an|a)$")


# A set to store all the inflight sponsored keywords
SPONSORED_KEYWORDS: Set[str] = set()


def make_keywords(words: List[str]):
    """Generate partial keywords."""
    prefix = " ".join(takewhile(SKIP_WORDS.match, words))
    unwords = " ".join(words)
    # If prefix is not empty, shift one (+1) for the followed whitespace
    begin = len(prefix) + 1 + MIN_KEYWORD_LEN if prefix else MIN_KEYWORD_LEN
    partials = [unwords[:i] for i in range(begin, len(unwords) + 1)]
    return list(
        islice(
            filterfalse(lambda x: x in SEEN_KEYWORDS or x in SPONSORED_KEYWORDS, partials),
            MAX_KEYWORDS,
        )
    )


def scan(
    language, data
) -> Generator[dict[str, str | list[str] | list[list[int]] | int], Any, None]:
    """Generate Suggestion."""
    for article in data:
        title = article["title"]
        keywords = make_keywords(title.lower().split("_"))
        title_string = title.replace("_", " ")
        wiki_title_string = "Wikipédia" if language == "fr" else "Wikipedia"

        if len(keywords) >= MIN_KEYWORDS:
            for keyword in keywords:
                SEEN_KEYWORDS.add(keyword)
            yield {
                "id": 0,  # FIXME: assign a suggestion ID.
                "url": f"{URL_PREFIX.format(language=language)}{quote(title)}",
                "iab_category": "5 - Education",
                "icon": ICON_ID,
                "advertiser": "Wikipedia",
                "title": f"{wiki_title_string} - {title_string}",
                "keywords": keywords,
                "full_keywords": [[title_string, len(keywords)]],
            }


def make_suggestions(language, want, data) -> list:
    """Construct Suggestions and write to json files."""
    gen = scan(language, data)
    results = list(islice(gen, want))
    print(f"Total suggestions: {len(results)}\n" f"Total keywords: {len(SEEN_KEYWORDS)}")
    return results
