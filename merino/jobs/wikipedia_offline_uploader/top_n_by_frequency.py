"""Extract the top "N" viewed pages from daily Wikipedia PageView API dumps.

`get_top_n_frequency()` accumulates page views across all daily input JSON files
in the given temp directory and returns the top N pages sorted by total views
in descending order. Internal pages and entries listed in
`page_ignore.csv` / `dynamic_wikipedia_blocklist.csv` are excluded. Fewer than
N entries may be returned if there aren't enough input pages.

Output shape:
    [
        {"title": "example_0", "rank": 1, "views": 100000},
        {"title": "example_1", "rank": 2, "views": 99999},
        ...
    ]
"""

import base64
import csv
import glob
import json
import os
import re
from collections import Counter

# Ignore the internal Wikipedia pages such as "Portal:Current_events",
# "Special:Search", "Wikipedia:About", "File:HispanTv.svg" etc.
#
# The title of the internal pages follows the pattern `\w:\w` except that the
# underscore is not used on neither sides of ":".
INTERNAL_PAGES = re.compile("[0-9A-Za-z]:[0-9A-Za-z]")


def process(page: str, ignored_titles: set[str]):
    """Process article and its page views."""
    top_pages: Counter = Counter()

    with open(page) as f:
        dump = json.load(f)
        for article in dump["items"][0]["articles"]:
            if (
                INTERNAL_PAGES.search(article["article"])
                or article["article"].casefold() in ignored_titles
            ):
                continue
            top_pages[article["article"]] += article["views"]

    return dict(top_pages)


def get_top_n_frequency(language, top_n, tempdir) -> list[dict]:
    """Extract the top N viewed pages for a given language."""
    merino_dir = os.getcwd()
    with (
        open(f"{merino_dir}/merino/jobs/wikipedia_offline_uploader/page_ignore.csv") as f,
        open(
            f"{merino_dir}/merino/jobs/wikipedia_offline_uploader/dynamic_wikipedia_blocklist.csv"
        ) as g,
    ):
        ignored = set(
            base64.b64decode(item["title"]).decode("utf-8") for item in csv.DictReader(f)
        )
        ignored |= set(
            base64.b64decode(item["title"]).decode("utf-8") for item in csv.DictReader(g)
        )

        top_pages: Counter = Counter()
        inputs = glob.glob(os.path.join(tempdir, f"{language}*.json"))

        for page in inputs:
            page_views = process(page, ignored)
            for title, views in page_views.items():
                top_pages[title] += views

        res = [
            {"title": title, "rank": n, "views": views}
            for n, (title, views) in enumerate(top_pages.most_common(top_n), start=1)
        ]

        return res
