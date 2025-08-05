"""This extracts the top "N" viewed pages from the most recent daily top
viewed pages fetched from Wikipedia PageView API. It does so by traversing from
the most recent pages to the least recent ones and terminates as soon as N
unique pages are extracted.

Note:
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

"""

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


def get_top_n_recency(language, top_n, tempdir) -> list[dict]:
    """Extract the top N viewed pages for a given language."""
    merino_dir = os.getcwd()
    with (
        open(f"{merino_dir}/merino/jobs/wikipedia_offline_uploader/page_ignore.csv") as f,
        open(
            f"{merino_dir}/merino/jobs/wikipedia_offline_uploader/dynamic_wikipedia_blocklist.csv"
        ) as g,
    ):
        ignored = set(item["title"].casefold() for item in csv.DictReader(f))
        ignored |= set(item["title"].casefold() for item in csv.DictReader(g))

    top_pages: Counter = Counter()
    for name in sorted(glob.glob(os.path.join(tempdir, f"{language}*.json"))):
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

    return res
