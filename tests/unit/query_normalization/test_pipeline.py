"""Unit tests for the query normalization pipeline."""

from merino.query_normalization.pipeline import (
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
def test_tier_a_casefold() -> None:
    """Uppercase input should be lowercased."""
    assert tier_a("AMAZON") == "amazon"


def test_tier_a_whitespace_collapse() -> None:
    """Multiple spaces should collapse to one."""
    assert tier_a("home   depot") == "home depot"


def test_tier_a_strip() -> None:
    """Leading and trailing whitespace should be removed."""
    assert tier_a("  amazon  ") == "amazon"


def test_tier_a_unicode_punct() -> None:
    """Smart quotes should be normalized to straight quotes."""
    assert tier_a("\u201chome depot\u201d") == '"home depot"'


def test_tier_a_em_dash() -> None:
    """Em dash should be normalized to hyphen."""
    assert tier_a("a\u2014b") == "a-b"


def test_tier_a_url_passthrough() -> None:
    """URL-like queries should skip NFKC and punct normalization."""
    assert tier_a("example.com/path") == "example.com/path"


def test_tier_a_email_passthrough() -> None:
    """Email-like queries should skip NFKC and punct normalization."""
    assert tier_a("user@example.com") == "user@example.com"


def test_tier_a_empty() -> None:
    """Empty input should return empty string."""
    assert tier_a("") == ""


def test_tier_a_nfkc() -> None:
    """Fullwidth characters should be normalized via NFKC."""
    assert tier_a("\uff21mazon") == "amazon"


# join normalize
def test_join_hit(canonical: set[str]) -> None:
    """Adjacent tokens that merge to a canonical term should be joined."""
    canonical.add("doordash")
    tokens = ["door", "dash"]
    assert _try_join_normalize(tokens, canonical) == "doordash"


def test_join_single_char_skip(canonical: set[str]) -> None:
    """Single-character tokens should not be merged."""
    canonical.add("models")
    tokens = ["model", "s"]
    assert _try_join_normalize(tokens, canonical) is None


def test_join_no_match(canonical: set[str]) -> None:
    """Non-canonical merges should return None."""
    tokens = ["purple", "elephant"]
    assert _try_join_normalize(tokens, canonical) is None


def test_join_single_token(canonical: set[str]) -> None:
    """Single token input should return None."""
    tokens = ["amazon"]
    assert _try_join_normalize(tokens, canonical) is None


def test_join_ambiguous(canonical: set[str]) -> None:
    """Ambiguous merges with single-char tokens should return None."""
    canonical.add("ab")
    canonical.add("bc")
    tokens = ["a", "b", "c"]
    assert _try_join_normalize(tokens, canonical) is None


def test_join_merged_in_canonical(canonical: set[str]) -> None:
    """Merge accepted when merged token alone is in canonical."""
    canonical.add("seatgeek")
    tokens = ["seat", "geek", "tickets"]
    result = _try_join_normalize(tokens, canonical)
    assert result == "seatgeek tickets"


# wordsegment
def test_wordsegment_fused_canonical(canonical: set[str]) -> None:
    """Fused token should be split when result is canonical."""
    canonical.add("home depot")
    result = _try_wordsegment(["homedepot"], canonical)
    assert result == "home depot"


def test_wordsegment_fused_with_extra_tokens(canonical: set[str]) -> None:
    """Fused token with extra tokens should split when segmented portion is canonical."""
    result = _try_wordsegment(["redsox", "game"], canonical)
    assert result == "red sox game"


def test_wordsegment_short_token_skip(canonical: set[str]) -> None:
    """Tokens shorter than 5 chars should be skipped."""
    result = _try_wordsegment(["abc"], canonical)
    assert result is None


def test_wordsegment_already_canonical(canonical: set[str]) -> None:
    """Tokens already in canonical should be skipped."""
    result = _try_wordsegment(["lakers"], canonical)
    assert result is None


def test_wordsegment_no_canonical_match(canonical: set[str]) -> None:
    """Split result not in canonical should return None."""
    result = _try_wordsegment(["purpleelephant"], canonical)
    assert result is None


# split_token
def test_split_canonical(canonical: set[str]) -> None:
    """Exhaustive split should find canonical form."""
    canonical.add("slick deals")
    result = _try_split_token("slickdeals", canonical)
    assert result == "slick deals"


def test_split_short_token(canonical: set[str]) -> None:
    """Tokens shorter than 4 chars should return None."""
    result = _try_split_token("abc", canonical)
    assert result is None


def test_split_no_match(canonical: set[str]) -> None:
    """Non-canonical splits should return None."""
    result = _try_split_token("xyzxyzxyz", canonical)
    assert result is None


# split_normalize
def test_split_normalize_success(canonical: set[str]) -> None:
    """Split normalize should return canonical form when split matches full query."""
    canonical.add("slick deals")
    result = _try_split_normalize(["slickdeals"], canonical)
    assert result == "slick deals"


def test_split_normalize_no_match(canonical: set[str]) -> None:
    """Split normalize should return None when no split matches."""
    result = _try_split_normalize(["xyzxyzxyz"], canonical)
    assert result is None


def test_split_normalize_short_skip(canonical: set[str]) -> None:
    """Split normalize should skip tokens shorter than 5 chars."""
    result = _try_split_normalize(["abc"], canonical)
    assert result is None


def test_split_normalize_already_canonical(canonical: set[str]) -> None:
    """Split normalize should skip tokens already in canonical."""
    result = _try_split_normalize(["lakers"], canonical)
    assert result is None


# build prefix index + prefix autocomplete
def test_build_prefix_index() -> None:
    """Prefix index should map prefixes to the highest-frequency word."""
    vocab = {"weather": 465297, "weatherford": 100}
    idx = build_prefix_index(vocab)
    entry = idx.get("weat")
    assert entry is not None
    assert entry[0] == "weather"


def test_build_prefix_index_second_best() -> None:
    """Prefix index should track second-best frequency."""
    vocab = {"weather": 465297, "weatherford": 100}
    idx = build_prefix_index(vocab)
    entry = idx.get("weath")
    assert entry is not None
    assert entry[0] == "weather"
    assert entry[2] == 100  # second best freq


def test_prefix_complete_last_token(
    prefix_index: dict[str, tuple[str, int, int]],
) -> None:
    """Partial last token should be completed."""
    result = _apply_prefix_complete("nyc weathe", prefix_index, set())
    assert result == "nyc weather"


def test_prefix_complete_last_token_sports(
    prefix_index: dict[str, tuple[str, int, int]],
) -> None:
    """Partial sports intent word should be completed."""
    result = _apply_prefix_complete("lakers game scor", prefix_index, set())
    assert result == "lakers game score"


def test_prefix_complete_already_complete(
    prefix_index: dict[str, tuple[str, int, int]],
) -> None:
    """Token in allowlist should not be completed."""
    result = _apply_prefix_complete("nyc weather", prefix_index, {"weather"})
    assert result == "nyc weather"


def test_prefix_complete_too_short(
    prefix_index: dict[str, tuple[str, int, int]],
) -> None:
    """Token shorter than min prefix length should not be completed."""
    result = _apply_prefix_complete("test nyc", prefix_index, set())
    assert result == "test nyc"


def test_prefix_complete_single_token(
    prefix_index: dict[str, tuple[str, int, int]],
) -> None:
    """Single token should still be completed by prefix complete."""
    result = _apply_prefix_complete("weathe", prefix_index, set())
    assert result == "weather"


def test_prefix_complete_low_freq() -> None:
    """Completion below min frequency should not fire."""
    idx = build_prefix_index({"weather": 100})  # below 3000 threshold
    result = _apply_prefix_complete("nyc weathe", idx, set())
    assert result == "nyc weathe"


def test_prefix_complete_ambiguous_ratio() -> None:
    """Completion with close second-best should not fire."""
    idx = build_prefix_index({"weather": 10000, "weatherford": 9000})
    result = _apply_prefix_complete("nyc weathe", idx, set())
    assert result == "nyc weathe"


def test_prefix_complete_empty_query() -> None:
    """Empty query should return unchanged."""
    idx = build_prefix_index({"weather": 465297})
    result = _apply_prefix_complete("", idx, set())
    assert result == ""


def test_prefix_complete_no_entry() -> None:
    """Token not in prefix index should return unchanged."""
    idx = build_prefix_index({"weather": 465297})
    result = _apply_prefix_complete("test zzzzz", idx, set())
    assert result == "test zzzzz"


def test_prefix_complete_already_best_word() -> None:
    """Token that is already the best word should not be completed."""
    idx = build_prefix_index({"weather": 465297})
    result = _apply_prefix_complete("nyc weather", idx, set())
    assert result == "nyc weather"


# bm25 reorder
def test_bm25_reorder(finance_bm25: BM25Index) -> None:
    """Query with same tokens in wrong order should be reordered."""
    result = finance_bm25.get_top_reorder("costco stock")
    assert result == "stock costco"


def test_bm25_already_canonical(finance_bm25: BM25Index) -> None:
    """Already-canonical query should return None."""
    result = finance_bm25.get_top_reorder("stock costco")
    assert result is None


def test_bm25_different_tokens(finance_bm25: BM25Index) -> None:
    """Query with tokens not in corpus should return None."""
    result = finance_bm25.get_top_reorder("purple elephant")
    assert result is None


def test_bm25_single_token(finance_bm25: BM25Index) -> None:
    """Single token query should return None."""
    result = finance_bm25.get_top_reorder("stock")
    assert result is None


def test_bm25_empty_scores() -> None:
    """Query with no matching terms should return None."""
    bm25 = BM25Index(["apple stock", "tesla stock"])
    result = bm25.get_top_reorder("xyz abc")
    assert result is None


# normalization e2e
def test_pipeline_exact_canonical_hit(
    pipeline: NormalizePipeline,
) -> None:
    """Query already in canonical should return unchanged."""
    assert pipeline.normalize("lakers") == "lakers"


def test_pipeline_casefold_to_canonical(
    pipeline: NormalizePipeline,
) -> None:
    """Uppercase canonical term should casefold to match."""
    assert pipeline.normalize("LAKERS") == "lakers"


def test_pipeline_wordsegment_fused(
    pipeline: NormalizePipeline,
) -> None:
    """Fused compound should be split to canonical form."""
    assert pipeline.normalize("redsox") == "red sox"


def test_pipeline_wordsegment_with_extra(
    pipeline: NormalizePipeline,
) -> None:
    """Fused compound with extra tokens should be split."""
    assert pipeline.normalize("redsox game") == "red sox game"


def test_pipeline_bm25_reorder(
    pipeline: NormalizePipeline,
) -> None:
    """Wrong word order should be reordered to canonical."""
    assert pipeline.normalize("costco stock") == "stock costco"


def test_pipeline_prefix_complete(
    pipeline: NormalizePipeline,
) -> None:
    """Partial last token should be completed."""
    assert pipeline.normalize("dow jone") == "dow jones"


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
    # "dow stoc" -> prefix complete -> "dow stock" (not canonical)
    # -> BM25 won't reorder (not a reorder case) -> returns "dow stock"
    result = p.normalize("dow stoc")
    assert result == "dow stock"


def test_pipeline_split_then_bm25() -> None:
    """Split normalize followed by BM25 reorder should work."""
    canonical = {"stock costco"}
    fin_bm25 = BM25Index(["stock costco"])
    p = NormalizePipeline(canonical=canonical, finance_bm25=fin_bm25)
    # "stockcostco" -> split -> "stock costco" -> already canonical from split
    result = p.normalize("stockcostco")
    assert result == "stock costco"


def test_pipeline_no_finance_bm25() -> None:
    """Pipeline without BM25 should still run other steps."""
    canonical = {"red sox", "lakers"}
    p = NormalizePipeline(canonical=canonical)
    assert p.normalize("redsox") == "red sox"
    assert p.normalize("lakers") == "lakers"


def test_pipeline_no_match_passthrough(
    pipeline: NormalizePipeline,
) -> None:
    """Non-matching query should pass through unchanged."""
    assert pipeline.normalize("purple elephant") == "purple elephant"


def test_pipeline_long_query_skips_split(
    pipeline: NormalizePipeline,
) -> None:
    """Queries with more than 2 tokens should skip split step."""
    assert pipeline.normalize("this is a long query") == "this is a long query"


def test_pipeline_empty_query(
    pipeline: NormalizePipeline,
) -> None:
    """Empty query should return empty string."""
    assert pipeline.normalize("") == ""


def test_pipeline_whitespace_only(
    pipeline: NormalizePipeline,
) -> None:
    """Whitespace-only query should return empty string."""
    assert pipeline.normalize("   ") == ""
