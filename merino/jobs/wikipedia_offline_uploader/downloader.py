"""Download and Retrieve Wiki articles and data."""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, UTC

import requests

from merino.jobs.wikipedia_offline_uploader.make_suggestions import make_suggestions
from merino.jobs.wikipedia_offline_uploader.top_n_by_frequency import get_top_n_frequency
from merino.jobs.wikipedia_offline_uploader.top_n_by_recency import get_top_n_recency

TOP_N = 7000


async def fetch_url(url, output_path) -> None:
    """Make a request to the specified URL and save the response."""
    # wikimedia asks to have a unique user agent https://www.mediawiki.org/wiki/Wikimedia_REST_API
    response = requests.get(
        url, headers={"User-Agent": "Mozilla/5.0 disco-team@mozilla.com"}, timeout=5
    )
    response.raise_for_status()
    with open(output_path, "w") as f:
        f.write(json.dumps(response.json()))


async def get_wiki_suggestions(language: str, relevance_type: str, access_type: str, days: int):
    """Get Wikipedia page view data and process them into suggestions."""
    results = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        languages = language.split(",")
        try:
            async with asyncio.TaskGroup() as task_group:
                for language in languages:
                    base_url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{language}.wikipedia.org/{access_type}"
                    for i in range(2, days + 2):
                        delta = i
                        dt = datetime.now(UTC) - timedelta(days=delta)
                        date_path = dt.strftime("%Y/%m/%d")
                        date_file = dt.strftime("%Y%m%d")
                        url = f"{base_url}/{date_path}"
                        output_path = os.path.join(tmpdir, f"{language}{date_file}.json")
                        task_group.create_task(
                            fetch_url(
                                url,
                                output_path,
                            )
                        )

        except* Exception as eg:
            for i, e in enumerate(eg.exceptions):
                print(f"{i}. {e}")
        for language in languages:
            if relevance_type == "frequency":
                data = get_top_n_frequency(language, TOP_N + 1000, tmpdir)

            else:
                data = get_top_n_recency(language, TOP_N + 1000, tmpdir)
            suggestions = make_suggestions(language, TOP_N, data)
            results[language] = suggestions
    return results
