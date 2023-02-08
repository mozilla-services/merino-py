"""Suggestion building/scoring tests"""
from merino.jobs.wikipedia_indexer.suggestion import Builder


def test_suggestion_builder():
    """Test to make sure the suggestion builder outputs a proper suggestion doc"""
    id = "1000"
    doc = {
        "title": "Hercule Poirot",
        "redirect": [
            {"namespace": 0, "title": "Poirot"},
        ],
        "heading": [
            "Overview",
        ],
        "external_link": [
            "https://www.oxfordlearnersdictionaries.com/definition/english/hercule-poirot",
        ],
        "text_bytes": 1000,
        "incoming_links": 10,
        "popularity_score": 0.0003,
        "create_timestamp": "2001-06-10T22:29:58Z",
        "page_id": 1000,
    }

    builder = Builder("v1")
    suggestion = builder.build(id, doc)

    assert suggestion["title"] == doc["title"]
    assert len(suggestion["suggest"]["input"]) == 1
    assert suggestion["suggest"]["input"][0] == doc["title"]
    assert suggestion["suggest"]["weight"] > 0

    assert len(suggestion["suggest-stop"]["input"]) == 1
    assert suggestion["suggest-stop"]["input"][0] == doc["title"]
    assert suggestion["suggest-stop"]["weight"] > 0
