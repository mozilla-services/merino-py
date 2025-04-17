#!/usr/bin/env python3
"""This script extracts the top "N" viewed pages from the most recent daily top
viewed pages fetched from Wikipedia PageView API. It does so by accumulating
page views from all the daily inputs in the `wikipedia-top-pages` directory.

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
    $ python top_n_by_frequency.py

    # Extract the top N viewed pages, e.g. top 5000
    $ python top_n_by_frequency.py 5000
"""

import csv
import glob
import json
import random
import re
import sys
from collections import Counter
from multiprocessing import Pool

# Ignore the internal Wikipedia pages such as "Portal:Current_events",
# "Special:Search", "Wikipedia:About", "File:HispanTv.svg" etc.
#
# The title of the internal pages follows the pattern `\w:\w` except that the
# underscore is not used on neither sides of ":".
INTERNAL_PAGES = re.compile("[0-9A-Za-z]:[0-9A-Za-z]")


def process(inputs):
    """Process article and its page views."""
    top_pages = Counter()
    for name in inputs:
        with open(name) as f:
            dump = json.load(f)
            for article in dump["items"][0]["articles"]:
                if (
                    INTERNAL_PAGES.search(article["article"])
                    or article["article"].casefold() in process.ignored_titles
                ):
                    continue
                top_pages[article["article"]] += article["views"]

    return dict(top_pages)


def initializer(ignored_titles):
    """Initialize for multiprocessing."""
    process.ignored_titles = ignored_titles


def main() -> None:
    """Extract the top N viewed pages for a given language."""
    language = "en"
    if len(sys.argv) < 2:
        top_n = 1000
    else:
        top_n = int(sys.argv[1])
    if len(sys.argv) == 3:
        language = sys.argv[2]

    with open("page_ignore.csv") as f, open("./dynamic_wikipedia_blocklist.csv") as g:
        ignored = set(item["title"].casefold() for item in csv.DictReader(f))
        ignored |= set(item["title"].casefold() for item in csv.DictReader(g))

    with Pool(None, initializer, [ignored]) as pool:
        top_pages: Counter = Counter()
        inputs = glob.glob(f"./wikipedia-top-pages/{language}*.json")
        random.shuffle(inputs)
        # Chunk the input list into sublists of 7
        tasks = [inputs[i : i + 7] for i in range(0, len(inputs), 7)]

        for page_views in pool.imap_unordered(process, tasks):
            for title, views in page_views.items():
                top_pages[title] += views

        res = [
            {"title": title, "rank": n, "views": views}
            for n, (title, views) in enumerate(top_pages.most_common(top_n), start=1)
        ]

        print(json.dumps(res, ensure_ascii=False), end="")


if __name__ == "__main__":
    main()
