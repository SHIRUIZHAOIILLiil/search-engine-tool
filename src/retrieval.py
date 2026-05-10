"""Retrieval algorithms (Lecture 13: query processing).

Different retrieval algorithms iterate the inverted index in different
orders to produce the same scored result list. This module collects the
pseudocode implementations from Lecture 13 alongside the
:class:`~src.ranker.Ranker` strategies, so swapping the ranker keeps the
algorithm intact and swapping the algorithm keeps the scores intact.

The first entry, :func:`document_at_a_time`, walks one document at a
time and accumulates each document's score in a single pass; later
commits will add term-at-a-time retrieval and conjunctive optimisation
alongside it.
"""

from __future__ import annotations

import heapq

from src.indexer import Index
from src.ranker import Ranker


def document_at_a_time(
    index: Index,
    query_tokens: list[str],
    ranker: Ranker,
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """Score documents one at a time and return the top-``k`` by relevance.

    Implements Lecture 13's "document-at-a-time retrieval" pseudocode
    with both optimisations called out in the lecture notes:

    1. Only documents that appear in at least one query term's posting
       list are scored (instead of looping over every document in the
       collection).
    2. A min-heap of bounded size keeps just the top ``top_k`` results
       in memory rather than scoring every candidate into a flat list.

    Args:
        index: The inverted index.
        query_tokens: Lowercased query tokens.
        ranker: A scoring strategy implementing the
            :class:`~src.ranker.Ranker` protocol (TF-IDF, BM25, ...).
        top_k: Maximum number of results to return; ``None`` returns
            every matching document.

    Returns:
        ``(doc_id, score)`` tuples sorted by score descending. Ties on
        score break on doc_id ascending so the order is deterministic.
    """
    candidate_ids: set[int] = set()
    for token in query_tokens:
        candidate_ids.update(index.postings.get(token, {}).keys())

    # The min-heap stores ``(score, -doc_id)``. heap[0] is therefore the
    # entry with the smallest score and, among tied scores, the largest
    # doc_id — i.e. the entry our tiebreak rule says is "worst" and
    # should be evicted first when a better candidate arrives.
    heap: list[tuple[float, int]] = []
    for doc_id in candidate_ids:
        score = ranker.score(index, query_tokens, doc_id)
        entry = (score, -doc_id)
        if top_k is None:
            heap.append(entry)
        elif len(heap) < top_k:
            heapq.heappush(heap, entry)
        elif entry > heap[0]:
            heapq.heapreplace(heap, entry)

    results = [(-neg_doc_id, score) for score, neg_doc_id in heap]
    results.sort(key=lambda pair: (-pair[1], pair[0]))
    return results


def term_at_a_time(
    index: Index,
    query_tokens: list[str],
    ranker: Ranker,
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """Score documents by sweeping each posting list start to finish.

    Implements Lecture 13's "term-at-a-time retrieval" pseudocode.
    For each query token we walk its posting list once, adding the
    per-token contribution to a hashtable of partial scores
    (accumulators). After every list has been processed, the
    accumulators are sorted and the top ``top_k`` are returned.

    Trade-offs against :func:`document_at_a_time` (Lecture 13 slide
    "term-at-a-time retrieval algorithm features"):

    * ✅ Each posting list is read sequentially with minimal disk
       seeking — efficient when lists live on disk.
    * ❌ Memory grows with the number of unique candidate documents,
       because every accumulator must stay alive until the last list
       has been processed.

    Assumes the ranker is **additive across query terms**: that is,
    ``score(q, d) == Σ_{t in q} score([t], d)``. Both
    :class:`~src.ranker.TFIDFRanker` and
    :class:`~src.ranker.BM25Ranker` satisfy this. A hypothetical
    proximity-aware ranker that cross-couples query terms would
    *not* work under TAAT and should use DAAT instead.

    Args:
        index: The inverted index.
        query_tokens: Lowercased query tokens.
        ranker: A scoring strategy implementing the
            :class:`~src.ranker.Ranker` protocol.
        top_k: Maximum results to return; ``None`` returns every match.

    Returns:
        ``(doc_id, score)`` tuples sorted by score descending; ties on
        score break on doc_id ascending so the order is deterministic
        and matches :func:`document_at_a_time` for additive rankers.
    """
    accumulators: dict[int, float] = {}
    for token in query_tokens:
        for doc_id in index.postings.get(token, {}):
            partial = ranker.score(index, [token], doc_id)
            accumulators[doc_id] = accumulators.get(doc_id, 0.0) + partial

    results = list(accumulators.items())
    results.sort(key=lambda pair: (-pair[1], pair[0]))
    if top_k is not None:
        results = results[:top_k]
    return results
