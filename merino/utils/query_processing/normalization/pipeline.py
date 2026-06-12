"""Precision-first query normalization cascade.

Steps run in order. Each step either returns a normalized result (short-circuiting
the rest of the pipeline) or returns None to pass control to the next step. If no
step produces a match, the pipeline returns the tier_a cleaned query unchanged.

Pipeline (in order):
  1. Tier A:           NFKC + punct normalization + casefold + whitespace collapse.
                       Always runs. Output is passed to all subsequent steps.

  2. Exact hit:        If query is already in the canonical set, return immediately.

  3. Join normalize:   Try merging adjacent tokens ("door dash" -> "doordash").
                       Returns on first unambiguous canonical hit, else falls through.

  4. Word segment:     Try splitting fused tokens ("homedepot" -> "home depot") using
                       a statistical bigram model from wordsegment python module. Falls
                       back to exhaustive split if wordsegment misses. Returns on
                       canonical hit, else falls through.

  5. Prefix complete:  Autocomplete the last partial token ("dow jone" -> "dow jones")
                       when one completion clearly dominates in the frequency index.
                       Only fires on multi-token queries. Updates the query but does
                       not short-circuit — the updated query is passed to step 6.

  6. BM25 reorder:     Reorder tokens to match a canonical form when the query has the
                       same tokens in a different order ("costco stock" -> "stock costco").
                       Returns the reordered form if found, else returns query as-is.
"""

import functools
import math
import re
import unicodedata
from collections import Counter
from itertools import combinations, pairwise

import wordsegment as _wordsegment

from merino.configs import settings
from merino.providers.suggest.flightaware.backends.airline_mappings import (
    NAME_TO_AIRLINE_CODE_MAPPING,
    VALID_AIRLINE_CODES,
)

# normalize unicode punctuation to ascii equivalents
_PUNCT_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u02bc": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2012": "-",
        "\u2015": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufeff": "",
    }
)


_WHITESPACE_RE = re.compile(r"\s+")


# Step 1: do canonicalization on the query string
def tier_a(query: str) -> str:
    """NFKC + punctuation normalization + casefold + whitespace collapse."""
    query = unicodedata.normalize("NFKC", query)
    query = query.translate(_PUNCT_MAP)
    return _WHITESPACE_RE.sub(" ", query.casefold().strip())


# Step 2 is exact hit check
# Step 3: check joined adjacent tokens for canonical form
def _try_join_normalize(tokens: list[str], canonical: set[str]) -> str | None:
    """Try merging each adjacent token pair; return canonical hit if unambiguous.

    Skips merges where either token is < 2 chars to prevent false joins.
    """
    hits: list[str] = []
    for i, (left, right) in enumerate(pairwise(tokens)):
        if len(left) < 2 or len(right) < 2:
            continue
        merged = f"{left}{right}"
        # form a new candidate with the joined adjacent tokens and the rest
        candidate = " ".join([*tokens[:i], merged, *tokens[i + 2 :]])
        if candidate in canonical or merged in canonical:
            hits.append(candidate)
            if len(hits) > 1:
                # abort normalization if ambiguous
                return None
    return hits[0] if len(hits) == 1 else None


# Step 4: segment query into tokens with wordsegment
_WORDSEGMENT_CACHE_SIZE: int = settings.query_normalization.wordsegment_cache_size


@functools.lru_cache(maxsize=_WORDSEGMENT_CACHE_SIZE)
def _ws_segment(tok: str) -> str:
    """Cache and return wordsegment splits for a token."""
    return " ".join(_wordsegment.segment(tok))


def _try_wordsegment(tokens: list[str], canonical: set[str]) -> str | None:
    """Try wordsegment on each fused token; accept if result is canonical.

    Accepts the rewrite if either the full rebuilt query OR the segmented
    portion alone is in canonical.
    """
    for i, tok in enumerate(tokens):
        if len(tok) < 5 or tok in canonical:
            continue
        segmented = _ws_segment(tok)
        if segmented == tok:
            continue
        # e.g. "redsox game" -> "red sox game"
        candidate = " ".join([*tokens[:i], segmented, *tokens[i + 1 :]])
        if candidate in canonical or segmented in canonical:
            return candidate
    return None


# Step 4: gated exhaustive split fallback (short queries only)
# helps in rare cases where wordsegment fails to segment a token
def _try_split_token(token: str, canonical: set[str], max_splits: int = 4) -> str | None:
    """Try splitting a fused token into space-separated canonical form.

    Tries 1 split, then 2, etc. up to max_splits.
    Each segment must be at least 2 chars.
    Example: "slickdeals" -> try all 1-split positions ->
             "slick deals" is in canonical -> return it.
    """
    n = len(token)
    if n < 4:
        return None

    min_seg = 2
    for num_splits in range(1, min(max_splits, n - 1)):
        # try every way to place num_splits cut points in the token
        # e.g. for "slickdeals", n=10, num_splits=1, cuts=[3] -> "slic kdeals"
        for cuts in combinations(range(min_seg, n - min_seg + 1), num_splits):
            parts: list[str] = []
            prev = 0
            # sentinel so the tail is checked inside the loop
            for cut in (*cuts, n):
                if cut - prev < min_seg:
                    break
                parts.append(token[prev:cut])
                prev = cut
            else:
                # only entered when the loop completes without breaking
                candidate = " ".join(parts)
                if candidate in canonical:
                    return candidate
    return None


def _try_split_normalize(tokens: list[str], canonical: set[str]) -> str | None:
    """Split each fused token; return canonical hit."""
    for i, tok in enumerate(tokens):
        if len(tok) < 5 or tok in canonical:
            continue

        split = _try_split_token(tok, canonical)
        if split is not None:
            candidate = " ".join([*tokens[:i], split, *tokens[i + 1 :]])
            if candidate in canonical:
                return candidate

    return None


# Step 5: Prefix Complete (multi-token queries only)
_AUTOCOMPLETE_MIN_PREFIX_LEN = 4  # minimum prefix length before autocomplete
_AUTOCOMPLETE_MIN_ABS_FREQ = 3_000  # minimum absolute frequency from vocab to allow autocomplete
_AUTOCOMPLETE_MIN_FREQ_RATIO = 2.0  # minimum gating ratio between best and second best
_AUTOCOMPLETE_COMMON_WORD_FREQ = (
    8_000_000  # wordsegment frequency guard to prevent autocomplete of common words
)


def build_prefix_index(
    vocab: dict[str, int],
    min_prefix_len: int = _AUTOCOMPLETE_MIN_PREFIX_LEN,
) -> dict[str, tuple[str, int, int]]:
    """Map each prefix to (best_word, best_freq, second_best_freq).
    e.g. "amaz" -> ("amazon", 50000, 10000) will autocomplete
    "amazon" has higher freq than next highest, "amazing" for example,
    in vocab
    """
    best: dict[str, tuple[str, int]] = {}
    second: dict[str, int] = {}

    for word, freq in vocab.items():
        if len(word) <= min_prefix_len:
            continue
        for end in range(min_prefix_len, len(word)):
            prefix = word[:end]
            if prefix not in best:
                best[prefix] = (word, freq)
            elif freq > best[prefix][1]:
                second[prefix] = best[prefix][1]
                best[prefix] = (word, freq)
            elif freq > second.get(prefix, 0):
                second[prefix] = freq

    return {p: (e[0], e[1], second.get(p, 0)) for p, e in best.items()}


def _apply_prefix_complete(
    query: str,
    tokens: list[str],
    prefix_index: dict[str, tuple[str, int, int]],
    allowlist: set[str],
    min_abs_freq: int = _AUTOCOMPLETE_MIN_ABS_FREQ,
) -> str:
    """Complete the last token only when one completion clearly dominates."""
    if not tokens:
        return query

    last = tokens[-1]
    # check if word in canonical, and don't autocomplete if so
    if len(last) < _AUTOCOMPLETE_MIN_PREFIX_LEN or last in allowlist:
        return query

    entry = prefix_index.get(last)
    if entry is None:
        return query

    best_word, best_freq, second_freq = entry
    if best_word == last:
        return query
    if best_freq < min_abs_freq:
        return query
    if second_freq > 0 and best_freq / second_freq < _AUTOCOMPLETE_MIN_FREQ_RATIO:
        return query

    tok_freq = _wordsegment.UNIGRAMS.get(last)
    # checks for common english words absent in our vocab
    # so we don't autocomplete them
    if tok_freq is not None and tok_freq >= _AUTOCOMPLETE_COMMON_WORD_FREQ:
        return query

    return " ".join([*tokens[:-1], best_word])


# Step 6: BM25 reorder (finance only for Phase 1)
class BM25Index:
    """Okapi BM25 over a fixed string corpus built once at startup."""

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        """Build the BM25 inverted index."""
        self.corpus = corpus  # keyword list (e.g. ["dow jones stock"])
        self.k1 = k1  # frequency saturation, how much repeating words matter
        self.b = b  # document length saturation, how much longer documents are penalized
        self._tokenized = [doc.split() for doc in corpus]
        self._corpus_set: set[str] = set(corpus)
        n = len(self.corpus)
        self._avgdl = sum(len(d) for d in self._tokenized) / max(
            n, 1
        )  # average document length across corpus
        self._doc_lens = [len(d) for d in self._tokenized]

        # counts how many documents each term appears in
        df: Counter[str] = Counter()
        for doc in self._tokenized:
            df.update(set(doc))

        # scores rarer terms more highly
        self._idf: dict[str, float] = {
            term: math.log((n - cnt + 0.5) / (cnt + 0.5) + 1) for term, cnt in df.items()
        }
        # Inverted index: maps each term to a list of (doc_index, term_frequency)
        # tuples. doc_index is the position in self.corpus, term_frequency is how
        # many times the term appears in that document.
        # e.g. {"stock": [(0, 1), (2, 1)]} means "stock" appears once in docs 0 and 2.
        self._inv: dict[str, list[tuple[int, int]]] = {}
        for i, doc in enumerate(self._tokenized):
            for term, count in Counter(doc).items():
                self._inv.setdefault(term, []).append((i, count))

    def get_top_reorder(self, query: str) -> str | None:
        """Return the best canonical form if it is a pure token reorder.

        Guards:
          1. Query must not already be canonical.
          2. Top match's sorted tokens must equal query's sorted tokens.
        """
        if query in self._corpus_set:
            return None

        q_tokens = query.split()
        if len(q_tokens) < 2:
            return None

        scores: dict[int, float] = {}
        # scoring loop for each term in the query
        # calculate for documents in corpus
        for term in set(q_tokens):
            if term not in self._inv:
                continue
            idf = self._idf.get(term, 0.0)
            for doc_idx, tf in self._inv[term]:
                dl = self._doc_lens[doc_idx]
                score = (
                    idf
                    * (tf * (self.k1 + 1))
                    / (tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl))
                )
                scores[doc_idx] = scores.get(doc_idx, 0.0) + score

        if not scores:
            return None

        # get top score and matching document index
        top_idx = max(scores, key=lambda i: scores[i])

        # guard to make sure we have the same tokens
        # for document and query (just reordered, not different)
        if sorted(q_tokens) != sorted(self._tokenized[top_idx]):
            return None

        return self.corpus[top_idx]


_FLIGHTAWARE_AIRLINE_SUFFIX_REWRITES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (" air lines", (" airlines", " airline", "")),
    (" air line", (" airlines", " airline", "")),
    (" airlines", (" airline", "")),
    (" airline", (" airlines", "")),
    (" airways", (" airway", "")),
    (" airway", (" airways", "")),
)


def _is_valid_flightaware_code(code: str, valid_codes: set[str]) -> bool:
    """Return whether the code is a usable FlightAware airline code."""
    code = code.upper()
    return code in valid_codes and any(char.isalpha() for char in code)


def _flightaware_airline_alias_variants(airline_name: str) -> set[str]:
    """Return safe mechanical aliases for a FlightAware airline name.

    Examples:
      - "delta airlines" -> {"delta airlines", "delta airline", "delta"}
      - "jetblue airways" -> {"jetblue airways", "jetblue airway", "jetblue"}

    The caller discards aliases that map to multiple codes.
    """
    normalized_name = tier_a(airline_name)
    if not normalized_name:
        return set()

    variants = {normalized_name}
    for suffix, replacements in _FLIGHTAWARE_AIRLINE_SUFFIX_REWRITES:
        if not normalized_name.endswith(suffix):
            continue

        base = normalized_name[: -len(suffix)]
        if not base:
            continue
        variants.update(tier_a(f"{base}{replacement}") for replacement in replacements)

    return {variant for variant in variants if variant}


def _build_flightaware_airline_aliases(valid_codes: set[str]) -> dict[str, str]:
    """Build FlightAware airline aliases from existing backend mapping data.

    The source map already has canonical airline names. This adds only mechanical
    singular/plural/suffix variants, and only keeps aliases that resolve to a
    single code in the existing data.

    e.g {"united airlines": "UA", "united airline": "UA", ...}
    """
    alias_candidates: dict[str, set[str]] = {}

    for airline_name, code in NAME_TO_AIRLINE_CODE_MAPPING.items():
        if not _is_valid_flightaware_code(code, valid_codes):
            continue

        code = code.upper()
        for alias in _flightaware_airline_alias_variants(airline_name):
            # set alias if not done yet and add matching code
            alias_candidates.setdefault(alias, set()).add(code)

    return {
        alias: next(iter(codes)) for alias, codes in alias_candidates.items() if len(codes) == 1
    }


# "ua 123" -> "ua123": normal code plus flight number, separated by whitespace.
_FLIGHTAWARE_CODE_NUMBER_RE = re.compile(r"^(?P<code>[a-z0-9]{1,3})\s+(?P<number>\d{1,5})$")

# "123 ua" -> "ua123": user typed the flight number before the airline code.
_FLIGHTAWARE_REVERSE_CODE_RE = re.compile(r"^(?P<number>\d{1,5})\s+(?P<code>[a-z0-9]{1,3})$")

# "123ua" -> "ua123": same reverse form, but with no whitespace.
_FLIGHTAWARE_REVERSE_CODE_COMPACT_RE = re.compile(
    r"^(?P<number>\d{1,5})(?P<code>[a-z][a-z0-9]{0,2})$"
)

# "ua-123", "ua#123", "ua:123", "ua/123" -> "ua123".
_FLIGHTAWARE_CODE_SEPARATOR_RE = re.compile(
    r"^(?P<code>[a-z0-9]{1,3})\s*[-#:/]\s*(?P<number>\d{1,5})$"
)

# "ua flight 123" -> "ua123": code plus literal "flight" before the number.
_FLIGHTAWARE_CODE_FLIGHT_NUMBER_RE = re.compile(
    r"^(?P<code>[a-z0-9]{1,3})\s+flight\s+(?P<number>\d{1,5})$"
)

# "united airlines flight 123" -> "ua123": airline name plus "flight" and number.
_FLIGHTAWARE_AIRLINE_NAME_FLIGHT_NUMBER_RE = re.compile(
    r"^(?P<airline>[a-z][a-z .&'-]{1,80})\s+flight\s+(?P<number>\d{1,5})$"
)

# "united airlines 123" -> "ua123": airline name immediately followed by a number.
_FLIGHTAWARE_AIRLINE_NAME_NUMBER_RE = re.compile(
    r"^(?P<airline>[a-z][a-z .&'-]{1,80})\s+(?P<number>\d{1,5})$"
)


class FlightAwareNormalizePipeline:
    """Conservative structural normalizer for FlightAware queries."""

    def __init__(
        self,
        valid_airline_codes: set[str] | None = None,
    ) -> None:
        """Initialize with valid airline codes from FlightAware mapping data."""
        self._valid_airline_codes = {
            code.upper() for code in (valid_airline_codes or VALID_AIRLINE_CODES)
        }
        self._airline_aliases = _build_flightaware_airline_aliases(self._valid_airline_codes)

    def _is_valid_code(self, code: str) -> bool:
        return _is_valid_flightaware_code(code, self._valid_airline_codes)

    def _normalize_code_number(self, code: str, number: str) -> str | None:
        code = code.upper()
        if not self._is_valid_code(code):
            return None
        return f"{code.casefold()}{number}"

    def _normalize_airline_number(self, airline: str, number: str) -> str | None:
        code = self._airline_aliases.get(tier_a(airline))
        if code is None:
            return None
        return self._normalize_code_number(code, number)

    def normalize(self, query: str) -> str:
        """Normalize a FlightAware query if it has a high-confidence flight shape."""
        q = tier_a(query)
        if not q:
            return q

        # first check airline codes
        code_number_matchers = (
            _FLIGHTAWARE_CODE_NUMBER_RE,
            _FLIGHTAWARE_REVERSE_CODE_RE,
            _FLIGHTAWARE_REVERSE_CODE_COMPACT_RE,
            _FLIGHTAWARE_CODE_SEPARATOR_RE,
            _FLIGHTAWARE_CODE_FLIGHT_NUMBER_RE,
        )
        for pattern in code_number_matchers:
            match = pattern.match(q)
            if match is None:
                continue
            normalized = self._normalize_code_number(
                match.group("code"),
                match.group("number"),
            )
            if normalized is not None:
                return normalized

        # next check full airline name
        airline_number_matchers = (
            _FLIGHTAWARE_AIRLINE_NAME_FLIGHT_NUMBER_RE,
            _FLIGHTAWARE_AIRLINE_NAME_NUMBER_RE,
        )
        for pattern in airline_number_matchers:
            match = pattern.match(q)
            if match is None:
                continue
            normalized = self._normalize_airline_number(
                match.group("airline"),
                match.group("number"),
            )
            if normalized is not None:
                return normalized

        return q


class NormalizePipeline:
    """Precision-first query normalization pipeline.

    Build once at startup; normalize() is cheap at query time.
    """

    def __init__(
        self,
        canonical: set[str],
        finance_bm25: BM25Index | None = None,
        canonical_prefix_index: (dict[str, tuple[str, int, int]] | None) = None,
        flightaware_pipeline: FlightAwareNormalizePipeline | None = None,
    ) -> None:
        """Initialize with pre-built components."""
        self._canonical = canonical
        self._fin_bm25 = finance_bm25
        self._canonical_prefix_index = canonical_prefix_index or {}
        self._canonical_words: set[str] = {w for phrase in canonical for w in phrase.split()}
        self._flightaware_pipeline = flightaware_pipeline or FlightAwareNormalizePipeline()

        # pre-warm cache on canonical words
        _wordsegment.load()
        for phrase in canonical:
            for tok in phrase.split():
                if len(tok) >= 5 and tok not in _wordsegment.UNIGRAMS:
                    _ws_segment(tok)

    # skip normalization for queries longer than this. The API already
    # rejects queries > 500 chars but this prevents excessive processing
    # from wordsegment and other expensive steps.
    _MAX_QUERY_LENGTH = 50

    def normalize(self, query: str) -> str:
        """Run the full normalization cascade."""
        q = tier_a(query)
        if not q or len(q) > self._MAX_QUERY_LENGTH:
            return q

        if q in self._canonical:
            return q

        tokens = q.split()

        # Step 3: join normalization
        joined = _try_join_normalize(tokens, self._canonical)
        if joined is not None:
            return joined

        # Step 4: word segmentation
        ws = _try_wordsegment(tokens, self._canonical)
        if ws is not None:
            return ws

        # Step 4b: exhaustive split fallback (short queries only)
        if len(tokens) <= 2:
            split = _try_split_normalize(tokens, self._canonical)
            if split is not None:
                if self._fin_bm25 is not None:
                    reordered = self._fin_bm25.get_top_reorder(split)
                    if reordered is not None:
                        split = reordered
                return split

        # Step 5: prefix complete (multi-token queries only)
        if self._canonical_prefix_index and len(tokens) >= 2:
            completed = _apply_prefix_complete(
                q,
                tokens,
                self._canonical_prefix_index,
                self._canonical_words,
            )
            if completed != q:
                if completed in self._canonical:
                    return completed
                q = completed

        # Step 6: BM25 reorder (finance only for Phase 1)
        if self._fin_bm25 is not None:
            reordered = self._fin_bm25.get_top_reorder(q)
            if reordered is not None:
                q = reordered

        return q

    def normalize_for_provider(self, query: str, provider_name: str) -> str:
        """Normalize a query using the pipeline for the requested provider."""
        if provider_name == "flightaware":
            return self._flightaware_pipeline.normalize(query)
        if provider_name in {"sports", "polygon"}:
            return self.normalize(query)
        return query
