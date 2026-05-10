"""Search operations over an inverted index."""

from __future__ import annotations

from src.indexer import Index
from src.ranker import Ranker, TFIDFRanker
from src.retrieval import conjunctive_retrieval, phrase_retrieval
from src.tokenizer import tokenize


def print_word(index: Index, word: str) -> dict[str, object]:
    """Return the posting list for one word, keyed by URL for display.

    Postings are stored against integer doc_ids internally; this view
    translates them back to URLs via :attr:`Index.documents` so the
    user sees the same shape they'd expect from the brief's example
    (``> print nonsense`` → URL → ``{frequency, positions}``).

    The query is tokenised under the index's stored
    :class:`~src.tokenizer.TokenizerConfig`, so if the index was built
    with stemming enabled the user can still print by the un-stemmed
    word (e.g. ``print running`` finds the stem ``run``).
    """
    tokens = tokenize(word, index.tokenizer_config)
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
    Lecture 12 ranking), implemented by delegation:

    1. :func:`~src.retrieval.conjunctive_retrieval` walks the sorted
       posting lists in lock-step (Lecture 13's "Processing Conjunctive
       Queries, Simple Algorithm") to keep only documents that contain
       *every* query token. This honours the brief's "all pages
       containing the words 'good' and 'friends'" requirement.
    2. The same call scores the surviving candidates with ``ranker``
       (TF-IDF by default) and orders them by score descending. Ties
       on score break on doc_id ascending so the order is deterministic.

    The query is tokenised under ``index.tokenizer_config`` so the same
    stemming / stopword choices that produced the index also apply to
    the query — keeping the two sides consistent.

    Returns:
        URLs ordered by relevance. The doc_id → URL mapping comes
        from :attr:`Index.documents`.
    """
    tokens = tokenize(query, index.tokenizer_config)
    if not tokens:
        return []

    if ranker is None:
        ranker = TFIDFRanker()

    results = conjunctive_retrieval(index, tokens, ranker)
    return [index.documents[doc_id] for doc_id, _ in results]


def find_phrase(
    index: Index,
    query: str,
    ranker: Ranker | None = None,
) -> list[str]:
    """Find pages where the query tokens occur as a consecutive phrase.

    Stricter than :func:`find_pages`: every query token must appear
    *adjacent and in order* in the document, not merely co-present.
    Routed via :func:`~src.retrieval.phrase_retrieval` which uses the
    position-offset intersection trick described in Lecture 13's
    "advanced query processing" topic.

    Surfaced by the CLI as ``find "good friends"`` — the quoted form
    disambiguates phrase intent from the conjunctive form
    ``find good friends`` that the brief specifies for unquoted input.

    The query is tokenised under ``index.tokenizer_config`` so the
    phrase match operates on the same vocabulary as the index.
    """
    tokens = tokenize(query, index.tokenizer_config)
    if not tokens:
        return []

    if ranker is None:
        ranker = TFIDFRanker()

    results = phrase_retrieval(index, tokens, ranker)
    return [index.documents[doc_id] for doc_id, _ in results]
