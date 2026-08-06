"""Extract the top "N" viewed pages by recency from daily Wikipedia PageView dumps.

`get_top_n_recency()` traverses daily input JSON files from most recent to least
recent and stops as soon as N unique pages have been collected. Internal pages and entries listed in `page_ignore.csv` /
`dynamic_wikipedia_blocklist.csv` are excluded. Fewer than N entries may be
returned if there aren't enough input pages. Results are sorted by view count
in descending order.

Output shape:
    [
        {"title": "example_0", "rank": 1, "views": 100000},
        {"title": "example_1", "rank": 2, "views": 99999},
        ...
    ]
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
