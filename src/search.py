"""Search operations over an inverted index."""

from __future__ import annotations

from src.indexer import InvertedIndex, tokenize


def print_word(index: InvertedIndex, word: str) -> dict[str, object]:
    """Return the posting list for one word."""
    tokens = tokenize(word)
    if not tokens:
        return {}
    return index.get(tokens[0], {})


def find_pages(index: InvertedIndex, query: str) -> list[str]:
    """Find pages containing every token in the query."""
    tokens = tokenize(query)
    if not tokens:
        return []

    posting_sets = [set(index.get(token, {}).keys()) for token in tokens]
    if not posting_sets:
        return []

    matching_pages = set.intersection(*posting_sets)
    return sorted(matching_pages)
