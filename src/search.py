"""Search operations over an inverted index."""

from __future__ import annotations

from src.indexer import Index, tokenize


def print_word(index: Index, word: str) -> dict[str, object]:
    """Return the posting list for one word, keyed by URL for display.

    Postings are stored against integer doc_ids internally; this view
    translates them back to URLs via :attr:`Index.documents` so the
    user sees the same shape they'd expect from the brief's example
    (``> print nonsense`` → URL → ``{frequency, positions}``).
    """
    tokens = tokenize(word)
    if not tokens:
        return {}
    raw = index.postings.get(tokens[0], {})
    return {index.documents[doc_id]: posting for doc_id, posting in raw.items()}


def find_pages(index: Index, query: str) -> list[str]:
    """Find pages containing every token in the query.

    Intersection happens on integer doc_id sets, then the surviving ids
    are translated to URLs and returned in sorted order.
    """
    tokens = tokenize(query)
    if not tokens:
        return []

    posting_sets = [set(index.postings.get(token, {}).keys()) for token in tokens]
    if not posting_sets:
        return []

    matching_ids = set.intersection(*posting_sets)
    return sorted(index.documents[doc_id] for doc_id in matching_ids)
