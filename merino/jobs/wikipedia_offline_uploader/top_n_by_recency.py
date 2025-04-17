#!/usr/bin/env python3
"""This script extracts the top "N" viewed pages from the most recent daily top
viewed pages fetched from Wikipedia PageView API. It does so by traversing from
the most recent pages to the least recent ones and terminates as soon as N
unique pages are extracted.

Note:
    * Before using this script, you should prepare the raw input files by using
      the script `fetch-wikipedia-top-pages.sh`. Make sure the raw pages are
      stored in the `wikipedia-top-pages` directory
    * It prints the extracted pages to stdout
    * The output is in JSON structured as:
        [
            {
                "title": "example_0",
                "rank": 1,
                "views": 100000
            },
            {
                "title": "example_1",
                "rank": 2,
                "views": 99999
            },
            ...
        ]
    * The output is sorted by the number of page views in descending order
    * It might return fewer than the requested N paged if there are not enough
      in the input files

Usage:

    # Extract the top 1000 viewed pages.
    $ python top_n_by_recency.py

    # Extract the top N viewed pages, e.g. top 5000
    $ python top_n_by_recency.py 5000
"""

import csv
import glob
import json
import re
import sys
from collections import Counter

# Ignore the internal Wikipedia pages such as "Portal:Current_events",
# "Special:Search", "Wikipedia:About", "File:HispanTv.svg" etc.
#
# The title of the internal pages follows the pattern `\w:\w` except that the
# underscore is not used on neither sides of ":".
INTERNAL_PAGES = re.compile("[0-9A-Za-z]:[0-9A-Za-z]")


def main() -> None:
    """Extract the top N viewed pages for a given language."""
    if len(sys.argv) < 2:
        top_n = 1000
    else:
        top_n = int(sys.argv[1])

    with open("page_ignore.csv") as f, open("./dynamic_wikipedia_blocklist.csv") as g:
        ignored = set(item["title"].casefold() for item in csv.DictReader(f))
        ignored |= set(item["title"].casefold() for item in csv.DictReader(g))

    top_pages: Counter = Counter()
    for name in sorted(glob.glob("./wikipedia-top-pages/*.json")):
        with open(name) as f:
            dump = json.loads(f.read())
            for article in dump["items"][0]["articles"]:
                if (
                    INTERNAL_PAGES.search(article["article"])
                    or article["article"].casefold() in ignored
                ):
                    continue
                top_pages[article["article"]] += article["views"]
            if len(top_pages) >= top_n:
                break

    res = [
        {"title": key, "rank": n, "views": views}
        for n, (key, views) in enumerate(top_pages.most_common(top_n), start=1)
    ]

    print(json.dumps(res, ensure_ascii=False), end="")


if __name__ == "__main__":
    main()
