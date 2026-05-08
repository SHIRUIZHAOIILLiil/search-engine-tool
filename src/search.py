"""Search operations over an inverted index."""

from __future__ import annotations

from src.indexer import Index, tokenize
from src.ranker import Ranker, TFIDFRanker


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


def find_pages(
    index: Index,
    query: str,
    ranker: Ranker | None = None,
) -> list[str]:
    """Find pages containing every query token, ordered by relevance.

    Two-stage retrieval (Lecture 13 conjunctive processing followed by
    Lecture 12 ranking):

    1. **AND filter** — keep only documents that contain *every* query
       token, as required by the brief ("all pages containing the
       words 'good' and 'friends'").
    2. **Rank** — score each surviving document with ``ranker`` (a
       :class:`~src.ranker.TFIDFRanker` if not supplied) and return
       URLs in descending score order. Ties break on ``doc_id``
       ascending so the order is deterministic when scores collide
       (e.g. when ``idf == 0`` because the term is in every document).
    """
    tokens = tokenize(query)
    if not tokens:
        return []

    if ranker is None:
        ranker = TFIDFRanker()

    posting_sets = [set(index.postings.get(token, {}).keys()) for token in tokens]
    if not posting_sets:
        return []
    matching_ids = set.intersection(*posting_sets)

    scored = [(doc_id, ranker.score(index, tokens, doc_id)) for doc_id in matching_ids]
    scored.sort(key=lambda pair: (-pair[1], pair[0]))

    return [index.documents[doc_id] for doc_id, _ in scored]
