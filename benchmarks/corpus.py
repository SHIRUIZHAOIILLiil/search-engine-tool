"""Deterministic synthetic corpus for benchmark scripts.

Produces lists of :class:`~src.crawler.CrawledPage` with the same
shape the real crawler emits, but generated offline and reproducibly
so benchmark numbers can be compared across runs and machines.

The parameter defaults match ``tests/test_performance.py``'s
in-test synthesizer (same seed, vocabulary pattern, length range)
so that performance-regression budgets and benchmark numbers
exercise the index against statistically identical workloads.
"""

from __future__ import annotations

import random

from src.crawler import CrawledPage

DEFAULT_SEED = 20260511
DEFAULT_VOCAB_SIZE = 200
DEFAULT_TOKENS_PER_PAGE = (30, 100)


def synthesize_pages(
    n_pages: int,
    *,
    seed: int = DEFAULT_SEED,
    vocab_size: int = DEFAULT_VOCAB_SIZE,
    tokens_per_page: tuple[int, int] = DEFAULT_TOKENS_PER_PAGE,
) -> list[CrawledPage]:
    """Return ``n_pages`` reproducible synthetic pages.

    Each page draws a token-count uniformly from ``tokens_per_page``
    (inclusive on both ends) and fills that many slots by sampling
    with replacement from a fixed ``word0000``..``word{vocab_size-1}``
    vocabulary. Sampling with replacement gives non-trivial term
    frequencies and a skewed posting-list length distribution — what
    real corpora look like in miniature.

    URLs are ``https://example.com/page-NNNN/`` zero-padded so
    deduplication on URL (the indexer's reuse-doc-id rule) cannot
    accidentally collapse two pages.

    Args:
        n_pages: How many pages to generate.
        seed: Random seed; the same seed always yields the same
            corpus byte-for-byte.
        vocab_size: How many distinct words exist in the universe.
            Smaller values make posting lists denser; larger values
            make them sparser.
        tokens_per_page: ``(min, max)`` inclusive bounds on page
            length in tokens.

    Returns:
        A list of length ``n_pages``. ``fields`` is left at the
        :class:`~src.parser.ParsedFields` default — the benchmark
        path only touches the body text, so structured fields would
        be dead weight.
    """
    if n_pages < 0:
        raise ValueError(f"n_pages must be non-negative, got {n_pages}")
    if vocab_size < 1:
        raise ValueError(f"vocab_size must be >= 1, got {vocab_size}")
    lo, hi = tokens_per_page
    if lo < 0 or hi < lo:
        raise ValueError(
            f"tokens_per_page must satisfy 0 <= min <= max, got {tokens_per_page}"
        )

    rng = random.Random(seed)
    vocab = [f"word{i:04d}" for i in range(vocab_size)]
    pages: list[CrawledPage] = []
    for i in range(n_pages):
        length = rng.randint(lo, hi)
        text = " ".join(rng.choice(vocab) for _ in range(length))
        pages.append(CrawledPage(url=f"https://example.com/page-{i:04d}/", text=text))
    return pages


_LOWERCASE_ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def synthesize_vocabulary(
    size: int,
    *,
    seed: int = DEFAULT_SEED,
    word_length_range: tuple[int, int] = (3, 12),
) -> list[str]:
    """Return ``size`` unique random lowercase words.

    Used by the v1.6.0 BK-tree benchmark to vary vocabulary size
    across the BKTREE_MIN_VOCAB threshold. Varied word lengths
    produce a more realistic edit-distance distribution than the
    ``wordNNNN`` pattern used by :func:`synthesize_pages` — the
    latter has nearly-identical lengths and a tight shared prefix,
    which would understate the work that real spelling correction
    has to do.

    Result is sorted for determinism so the same ``(size, seed)``
    pair always returns the same list in the same order.
    """
    if size < 0:
        raise ValueError(f"size must be non-negative, got {size}")
    lo, hi = word_length_range
    if lo < 1 or hi < lo:
        raise ValueError(
            f"word_length_range must satisfy 1 <= min <= max, got {word_length_range}"
        )

    rng = random.Random(seed)
    vocab: set[str] = set()
    # Bound the inner loop generously — the birthday-paradox-style
    # collision rate stays manageable for any size <= 10**6 / |alphabet|^|word_length|.
    max_attempts = max(10 * size, 1000)
    attempts = 0
    while len(vocab) < size and attempts < max_attempts:
        word_len = rng.randint(lo, hi)
        word = "".join(rng.choices(_LOWERCASE_ALPHABET, k=word_len))
        vocab.add(word)
        attempts += 1
    if len(vocab) < size:
        raise RuntimeError(
            f"failed to generate {size} unique words within "
            f"{max_attempts} attempts; widen word_length_range"
        )
    return sorted(vocab)


def synthesize_clustered_vocabulary(
    size: int,
    *,
    seed: int = DEFAULT_SEED,
    n_stems: int | None = None,
    stem_length_range: tuple[int, int] = (3, 7),
    suffixes: tuple[str, ...] = (
        "", "s", "ed", "ing", "ly", "er", "est",
        "ness", "ment", "ity", "ish", "able",
    ),
) -> list[str]:
    """Generate a stem-plus-suffix vocabulary that clusters by edit distance.

    Real English vocabularies cluster heavily — ``friend``,
    ``friends``, ``friendly``, ``friendship`` are all within a few
    edits of each other. This generator models that pattern: a small
    pool of random stems gets combined with a fixed family of common
    English suffixes, producing a vocabulary whose edit-distance
    distribution is concentrated rather than uniform.

    BK-tree's triangle-inequality pruning shines on this shape
    because most subtrees centred on a given stem fall entirely
    inside or entirely outside a small distance ball around the
    query — exactly the case the BK-tree algorithm was designed for.
    On uniform-random vocabularies the pruning is weak because every
    distance is roughly the same; on a clustered vocabulary the
    pruning is sharp because distances vary widely.

    Args:
        size: Number of unique terms to generate.
        seed: Random seed for reproducibility.
        n_stems: Size of the stem pool; default scales as
            ``max(20, size // 5)`` so the theoretical max combinations
            (``n_stems * len(suffixes)``) comfortably exceeds ``size``,
            leaving room for the random sampler to find unique combos.
            On a 5 000-word vocab this yields ~1 000 stems with ~5
            variations per family — realistic for English morphology.
        stem_length_range: Length bounds for stems before suffixing.
        suffixes: Tuple of suffixes to combine with each stem.
            Always includes ``""`` so the bare stem is in the vocab.

    Result is sorted for determinism.
    """
    if size < 0:
        raise ValueError(f"size must be non-negative, got {size}")
    if n_stems is None:
        n_stems = max(20, size // 5)
    if n_stems < 1:
        raise ValueError(f"n_stems must be positive, got {n_stems}")

    rng = random.Random(seed)
    lo, hi = stem_length_range
    stems = []
    seen_stems: set[str] = set()
    while len(stems) < n_stems:
        word_len = rng.randint(lo, hi)
        stem = "".join(rng.choices(_LOWERCASE_ALPHABET, k=word_len))
        if stem not in seen_stems:
            seen_stems.add(stem)
            stems.append(stem)

    vocab: set[str] = set()
    max_attempts = max(10 * size, 1000)
    attempts = 0
    while len(vocab) < size and attempts < max_attempts:
        stem = rng.choice(stems)
        suffix = rng.choice(suffixes)
        vocab.add(stem + suffix)
        attempts += 1
    if len(vocab) < size:
        raise RuntimeError(
            f"failed to generate {size} unique clustered words; "
            f"increase n_stems or widen suffixes"
        )
    return sorted(vocab)


def make_typo(word: str, n_edits: int, rng: random.Random) -> str:
    """Apply ``n_edits`` random insertions / deletions / substitutions.

    Targets for the suggest benchmark come from this — given a known
    vocabulary term and ``n_edits=1`` or ``2``, we produce a string
    that is exactly that many edits away (or very close to — single-
    char deletions on length-1 strings are no-ops, so the actual
    distance may be smaller, but never greater).

    Operates on the local ``rng`` so the caller can keep different
    streams deterministic without crosstalk.
    """
    if n_edits < 0:
        raise ValueError(f"n_edits must be non-negative, got {n_edits}")
    if not word:
        raise ValueError("word must be non-empty")

    result = list(word)
    for _ in range(n_edits):
        op = rng.choice(("substitute", "insert", "delete"))
        if op == "substitute" and result:
            i = rng.randrange(len(result))
            result[i] = rng.choice(_LOWERCASE_ALPHABET)
        elif op == "insert":
            i = rng.randrange(len(result) + 1)
            result.insert(i, rng.choice(_LOWERCASE_ALPHABET))
        elif op == "delete" and len(result) > 1:
            i = rng.randrange(len(result))
            result.pop(i)
        # Length-1 + delete is a no-op (we never produce empty strings);
        # leaves result unchanged this round, but the loop still
        # terminates after n_edits iterations.
    return "".join(result)
