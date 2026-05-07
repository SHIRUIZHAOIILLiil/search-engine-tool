"""Search operations over an inverted index."""

from __future__ import annotations

from src.indexer import Index, tokenize


def print_word(index: Index, word: str) -> dict[str, object]:
    """Return the posting list for one word."""
    tokens = tokenize(word)
    if not tokens:
        return {}
    return index.data.get(tokens[0], {})


def find_pages(index: Index, query: str) -> list[str]:
    """Find pages containing every token in the query."""
    tokens = tokenize(query)
    if not tokens:
        return []

    posting_sets = [set(index.data.get(token, {}).keys()) for token in tokens]
    if not posting_sets:
        return []

    matching_pages = set.intersection(*posting_sets)
    return sorted(matching_pages)
