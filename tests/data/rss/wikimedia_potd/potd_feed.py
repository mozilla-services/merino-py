"""Loads a sample RSS response from the Wikimedia Picture of the Day feed, used for testing.

The raw feed is stored verbatim in ``potd_feed.xml`` (rather than embedded as a Python string)
so the test fixture matches the actual RSS payload received in production, with no
string-encoding step in between that could introduce a discrepancy.
"""

from pathlib import Path

TEST_RSS_FEED: str = (Path(__file__).parent / "potd_feed.xml").read_text(encoding="utf-8")
