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
