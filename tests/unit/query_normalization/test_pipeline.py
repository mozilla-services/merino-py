"""Unit tests for the query normalization pipeline."""

import pytest

from merino.utils.query_processing.normalization.pipeline import (
    BM25Index,
    NormalizePipeline,
    _apply_prefix_complete,
    _try_join_normalize,
    _try_split_normalize,
    _try_split_token,
    _try_wordsegment,
    build_prefix_index,
    tier_a,
)


# tier_a
@pytest.mark.parametrize(
    "input_query, expected",
    [
        ("AMAZON", "amazon"),
        ("home   depot", "home depot"),
        ("  amazon  ", "amazon"),
        ("\u201chome depot\u201d", '"home depot"'),
        ("a\u2014b", "a-b"),
        ("example.com/path", "example.com/path"),
        ("user@example.com", "user@example.com"),
        ("", ""),
        ("\uff21mazon", "amazon"),
    ],
    ids=[
        "casefold",
        "whitespace_collapse",
        "strip",
        "unicode_punct",
        "em_dash",
        "url_unchanged",
        "email_unchanged",
        "empty",
        "nfkc",
    ],
)
def test_tier_a(input_query: str, expected: str) -> None:
    """Verify tier_a canonicalization for various input types."""
    assert tier_a(input_query) == expected


# join normalize
def test_join_hit(canonical: set[str]) -> None:
    """Adjacent tokens that merge to a canonical term should be joined."""
    canonical.add("doordash")
    assert _try_join_normalize(["door", "dash"], canonical) == "doordash"


def test_join_single_char_skip(canonical: set[str]) -> None:
    """Single-character tokens should not be merged."""
    canonical.add("models")
    assert _try_join_normalize(["model", "s"], canonical) is None


def test_join_no_match(canonical: set[str]) -> None:
    """Non-canonical merges should return None."""
    assert _try_join_normalize(["purple", "elephant"], canonical) is None


def test_join_single_token(canonical: set[str]) -> None:
    """Single token input should return None. Only multi-token inputs can be merged."""
    assert _try_join_normalize(["amazon"], canonical) is None


def test_join_ambiguous(canonical: set[str]) -> None:
    """Ambiguous merges with single-char tokens should return None."""
    canonical.add("ab")
    canonical.add("bc")
    assert _try_join_normalize(["a", "b", "c"], canonical) is None


def test_join_merged_in_canonical(canonical: set[str]) -> None:
    """Merge accepted when merged token alone is in canonical."""
    canonical.add("seatgeek")
    assert _try_join_normalize(["seat", "geek", "tickets"], canonical) == "seatgeek tickets"


# wordsegment
def test_wordsegment_fused_canonical(canonical: set[str]) -> None:
    """Fused token should be split when result is canonical."""
    canonical.add("home depot")
    assert _try_wordsegment(["homedepot"], canonical) == "home depot"


def test_wordsegment_fused_with_extra_tokens(canonical: set[str]) -> None:
    """Fused token with extra tokens should split when segmented portion is canonical."""
    assert _try_wordsegment(["redsox", "game"], canonical) == "red sox game"


def test_wordsegment_short_token_skip(canonical: set[str]) -> None:
    """Tokens shorter than 5 chars should be skipped."""
    assert _try_wordsegment(["abc"], canonical) is None


def test_wordsegment_already_canonical(canonical: set[str]) -> None:
    """Tokens already in canonical should be skipped."""
    assert _try_wordsegment(["lakers"], canonical) is None


def test_wordsegment_no_canonical_match(canonical: set[str]) -> None:
    """Split result not in canonical should return None."""
    assert _try_wordsegment(["purpleelephant"], canonical) is None


# split_token
@pytest.mark.parametrize(
    "token, extra_canonical, expected",
    [
        ("slickdeals", {"slick deals"}, "slick deals"),
        ("abc", set(), None),
        ("xyzxyzxyz", set(), None),
    ],
    ids=["canonical_hit", "short_token", "no_match"],
)
def test_split_token(
    canonical: set[str], token: str, extra_canonical: set[str], expected: str | None
) -> None:
    """Verify exhaustive split for various inputs."""
    canonical.update(extra_canonical)
    assert _try_split_token(token, canonical) == expected


# split_normalize
@pytest.mark.parametrize(
    "tokens, extra_canonical, expected",
    [
        (["slickdeals"], {"slick deals"}, "slick deals"),
        (["xyzxyzxyz"], set(), None),
        (["abc"], set(), None),
        (["lakers"], set(), None),
    ],
    ids=["success", "no_match", "short_skip", "already_canonical"],
)
def test_split_normalize(
    canonical: set[str], tokens: list[str], extra_canonical: set[str], expected: str | None
) -> None:
    """Verify split normalize for various inputs."""
    canonical.update(extra_canonical)
    assert _try_split_normalize(tokens, canonical) == expected


# build prefix index
@pytest.mark.parametrize(
    "vocab, prefix, expected_word, expected_second",
    [
        ({"weather": 465297}, "weat", "weather", 0),
        ({"weather": 465297, "weatherford": 100}, "weath", "weather", 100),
        ({"weatherford": 100, "weather": 465297}, "weath", "weather", 100),
        ({"weather": 465297, "weatherford": 100, "weatherly": 5000}, "weath", "weather", 5000),
    ],
    ids=["basic", "second_best", "replaces_best", "updates_second"],
)
def test_build_prefix_index(
    vocab: dict[str, int], prefix: str, expected_word: str, expected_second: int
) -> None:
    """Verify prefix index construction."""
    idx = build_prefix_index(vocab)
    entry = idx.get(prefix)
    assert entry is not None
    assert entry[0] == expected_word
    assert entry[2] == expected_second


def test_build_prefix_index_short_words_skipped() -> None:
    """Words shorter than min prefix length should be skipped."""
    idx = build_prefix_index({"the": 1000000, "weather": 465297})
    assert "the" not in idx
    assert "weat" in idx


# prefix autocomplete
@pytest.mark.parametrize(
    "query, tokens, expected",
    [
        ("nyc weathe", ["nyc", "weathe"], "nyc weather"),
        ("lakers game scor", ["lakers", "game", "scor"], "lakers game score"),
        ("weathe", ["weathe"], "weather"),
    ],
    ids=["last_token", "sports_intent", "single_token"],
)
def test_prefix_complete_fires(
    prefix_index: dict[str, tuple[str, int, int]],
    query: str,
    tokens: list[str],
    expected: str,
) -> None:
    """Verify prefix completion fires when expected."""
    assert _apply_prefix_complete(query, tokens, prefix_index, set()) == expected


@pytest.mark.parametrize(
    "query, tokens, allowlist, expected",
    [
        ("nyc weather", ["nyc", "weather"], {"weather"}, "nyc weather"),
        ("test nyc", ["test", "nyc"], set(), "test nyc"),
    ],
    ids=["in_allowlist", "too_short"],
)
def test_prefix_complete_skips(
    prefix_index: dict[str, tuple[str, int, int]],
    query: str,
    tokens: list[str],
    allowlist: set[str],
    expected: str,
) -> None:
    """Verify prefix completion skips when expected."""
    assert _apply_prefix_complete(query, tokens, prefix_index, allowlist) == expected


def test_prefix_complete_low_freq() -> None:
    """Completion below min frequency should not fire."""
    idx = build_prefix_index({"weather": 100})
    assert _apply_prefix_complete("nyc weathe", ["nyc", "weathe"], idx, set()) == "nyc weathe"


def test_prefix_complete_ambiguous_ratio() -> None:
    """Completion with close second-best should not fire."""
    idx = build_prefix_index({"weather": 10000, "weatherford": 9000})
    assert _apply_prefix_complete("nyc weathe", ["nyc", "weathe"], idx, set()) == "nyc weathe"


def test_prefix_complete_empty_query() -> None:
    """Empty query should return unchanged."""
    idx = build_prefix_index({"weather": 465297})
    assert _apply_prefix_complete("", [], idx, set()) == ""


def test_prefix_complete_no_entry() -> None:
    """Token not in prefix index should return unchanged."""
    idx = build_prefix_index({"weather": 465297})
    assert _apply_prefix_complete("test zzzzz", ["test", "zzzzz"], idx, set()) == "test zzzzz"


def test_prefix_complete_already_best_word() -> None:
    """Token that is already the best word should not be completed."""
    idx = build_prefix_index({"weather": 465297})
    assert _apply_prefix_complete("nyc weather", ["nyc", "weather"], idx, set()) == "nyc weather"


# bm25 reorder
@pytest.mark.parametrize(
    "query, expected",
    [
        ("costco stock", "stock costco"),
        ("stock costco", None),
        ("purple elephant", None),
        ("stock", None),
    ],
    ids=["reorder", "already_canonical", "different_tokens", "single_token"],
)
def test_bm25_reorder(finance_bm25: BM25Index, query: str, expected: str | None) -> None:
    """Verify BM25 reorder for various inputs."""
    assert finance_bm25.get_top_reorder(query) == expected


def test_bm25_empty_scores() -> None:
    """Query with no matching terms should return None."""
    bm25 = BM25Index(["apple stock", "tesla stock"])
    assert bm25.get_top_reorder("xyz abc") is None


# normalization e2e
@pytest.mark.parametrize(
    "query, expected",
    [
        ("lakers", "lakers"),
        ("LAKERS", "lakers"),
        ("redsox", "red sox"),
        ("redsox game", "red sox game"),
        ("costco stock", "stock costco"),
        ("dow jone", "dow jones"),
        ("purple elephant", "purple elephant"),
        ("", ""),
        ("   ", ""),
    ],
    ids=[
        "exact_canonical",
        "casefold",
        "wordsegment_fused",
        "wordsegment_with_extra",
        "bm25_reorder",
        "prefix_complete",
        "no_match_passthrough",
        "empty",
        "whitespace_only",
    ],
)
def test_pipeline_normalize(pipeline: NormalizePipeline, query: str, expected: str) -> None:
    """Verify end-to-end normalization for various inputs."""
    assert pipeline.normalize(query) == expected


def test_pipeline_prefix_complete_non_canonical(
    canonical: set[str],
    finance_bm25: BM25Index,
) -> None:
    """Prefix complete result not in canonical should still update query for BM25."""
    prefix_idx = build_prefix_index({"weather": 465297, "stock": 193730})
    p = NormalizePipeline(
        canonical=canonical,
        finance_bm25=finance_bm25,
        canonical_prefix_index=prefix_idx,
    )
    assert p.normalize("dow stoc") == "dow stock"


def test_pipeline_split_then_bm25() -> None:
    """Split normalize followed by BM25 reorder should work."""
    canonical = {"stock costco"}
    fin_bm25 = BM25Index(["stock costco"])
    p = NormalizePipeline(canonical=canonical, finance_bm25=fin_bm25)
    assert p.normalize("stockcostco") == "stock costco"


def test_pipeline_split_then_bm25_reorder() -> None:
    """Split result should be reordered by BM25 when applicable."""
    canonical = {"zaxby treats"}
    fin_bm25 = BM25Index(["treats zaxby"])
    p = NormalizePipeline(canonical=canonical, finance_bm25=fin_bm25)
    assert p.normalize("zaxbytreats") == "treats zaxby"


def test_pipeline_split_no_bm25() -> None:
    """Split without BM25 should return split result directly."""
    canonical = {"zaxby treats"}
    p = NormalizePipeline(canonical=canonical)
    assert p.normalize("zaxbytreats") == "zaxby treats"


def test_pipeline_no_finance_bm25() -> None:
    """Pipeline without BM25 should still run other steps."""
    canonical = {"red sox", "lakers"}
    p = NormalizePipeline(canonical=canonical)
    assert p.normalize("redsox") == "red sox"
    assert p.normalize("lakers") == "lakers"


def test_pipeline_prefix_then_bm25_reorder() -> None:
    """Prefix complete result should be passed to BM25 reorder."""
    canonical = {"stock costco"}
    fin_bm25 = BM25Index(["stock costco"])
    prefix_idx = build_prefix_index({"costco": 100000, "stock": 193730})
    p = NormalizePipeline(
        canonical=canonical,
        finance_bm25=fin_bm25,
        canonical_prefix_index=prefix_idx,
    )
    assert p.normalize("foo costc") == "foo costco"


def test_pipeline_long_query_skips_split(pipeline: NormalizePipeline) -> None:
    """Queries with more than 2 tokens should skip split step."""
    assert pipeline.normalize("this is a long query") == "this is a long query"
