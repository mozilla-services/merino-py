"""Test blocklist functionality"""

import json
import os
import tempfile

from merino.jobs.navigational_suggestions import BlocklistActions, blocklist
from merino.jobs.navigational_suggestions.utils import load_blocklist, write_blocklist


def test_blocklist():
    """Test the blocklist command functionality."""
    top_picks_path = ""
    blocklist_path = ""

    try:
        block_list = load_blocklist("tests/data/domain_blocklist.json")
        # write to a temporary location
        _, blocklist_path = tempfile.mkstemp()
        write_blocklist(block_list, blocklist_path)

        blocklist(BlocklistActions.add, "baz", blocklist_path)

        assert "baz" in load_blocklist(blocklist_path)

        blocklist(BlocklistActions.remove, "baz", blocklist_path)

        assert "baz" not in load_blocklist(blocklist_path)

        top_pick_data = {
            "domains": [
                {
                    "rank": 1,
                    "title": "Example",
                    "domain": "example",
                    "url": "https://example.com",
                    "icon": "",
                    "categories": ["web-browser"],
                    "similars": [],
                },
                {
                    "rank": 2,
                    "title": "Foo",
                    "domain": "foo",
                    "url": "https://foo.com",
                    "icon": "",
                },
            ]
        }
        _, top_picks_path = tempfile.mkstemp()
        json.dump(top_pick_data, open(top_picks_path, "w"))

        blocklist(BlocklistActions.add, "foo", blocklist_path)
        blocklist(
            BlocklistActions.apply,
            blocklist_path=blocklist_path,
            top_picks_path=top_picks_path,
        )

        updated_top_picks = json.load(open(top_picks_path, "r"))
        assert "example" in [d["domain"] for d in updated_top_picks["domains"]]
        assert "foo" not in [d["domain"] for d in updated_top_picks["domains"]]

    finally:
        os.remove(blocklist_path)
        os.remove(top_picks_path)
