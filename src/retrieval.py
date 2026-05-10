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
import math

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


def conjunctive_match(
    index: Index,
    query_tokens: list[str],
) -> list[int]:
    """Return doc_ids appearing in *every* query token's posting list.

    Implements Lecture 13's "Processing Conjunctive Queries, Simple
    Algorithm" (slide 17), generalised from two lists to N. Each query
    term's posting list is walked in sorted doc_id order using a
    pointer; on every iteration we look at the current doc_id at each
    pointer and:

    * Append a match if every pointer agrees on the same doc_id, then
      advance every pointer.
    * Otherwise advance every pointer whose current value lags behind
      the largest current value (these are the "smaller" pointers in
      L13's two-list pseudocode generalised to N).

    Whichever list is exhausted first stops the loop. The result is
    ascending by doc_id, ready for downstream scoring.
    """
    if not query_tokens:
        return []

    sorted_lists: list[list[int]] = []
    for token in query_tokens:
        postings = index.postings.get(token)
        if not postings:
            # Any term with no postings makes a conjunctive match impossible.
            return []
        sorted_lists.append(sorted(postings.keys()))

    pointers = [0] * len(sorted_lists)
    matches: list[int] = []

    while all(pointers[i] < len(sorted_lists[i]) for i in range(len(sorted_lists))):
        currents = [sorted_lists[i][pointers[i]] for i in range(len(sorted_lists))]
        max_doc = max(currents)
        if all(c == max_doc for c in currents):
            matches.append(max_doc)
            for i in range(len(pointers)):
                pointers[i] += 1
        else:
            # Inner while skips past several too-small entries in one
            # pass — important when one list is much shorter than the
            # others (a typical "rare term + common term" query).
            for i in range(len(pointers)):
                while (
                    pointers[i] < len(sorted_lists[i])
                    and sorted_lists[i][pointers[i]] < max_doc
                ):
                    pointers[i] += 1

    return matches


def _advance_pointer(sorted_list: list[int], pointer: int, target: int) -> int:
    """Advance ``pointer`` in ``sorted_list`` until ``list[pointer] >= target``.

    Implements Lecture 13's skip-pointer scheme (slides 18-23): big
    ``sqrt(remaining)`` jumps while still safely below ``target``, then
    a linear scan over the last bucket. ``sqrt(n)`` is the textbook
    skip-distance heuristic — it balances jump count against scan
    length, giving O(sqrt(n)) work for a single advance.

    L13's worked formula ``kn/c + pc/2`` uses bytes; this function
    operates on entries (Python ints) instead, but the algebra is
    identical with "entry count" substituted for "byte count".
    """
    n = len(sorted_list)
    if pointer >= n or sorted_list[pointer] >= target:
        return pointer

    step = max(1, int(math.sqrt(n - pointer)))

    # Big jumps while a full step stays strictly below the target.
    while pointer + step < n and sorted_list[pointer + step] < target:
        pointer += step

    # Linear scan over the final ``step``-sized window (or off the end).
    while pointer < n and sorted_list[pointer] < target:
        pointer += 1

    return pointer


def conjunctive_match_with_skip(
    index: Index,
    query_tokens: list[str],
) -> list[int]:
    """Conjunctive intersection with Lecture 13 skip-pointer optimisation.

    Produces results identical to :func:`conjunctive_match` but advances
    lagging pointers in ``sqrt(remaining_length)`` jumps instead of one
    entry at a time. For the canonical skewed query (one rare term, one
    common term — L13's "galago / animal" example), this turns a near-
    full scan of the long list into roughly ``sqrt(N)`` work.

    The equivalence with the simpler algorithm is pinned by a
    property-based test in ``test_retrieval.py`` over many random
    posting layouts; if you change either function, that test will
    catch the divergence.
    """
    if not query_tokens:
        return []

    sorted_lists: list[list[int]] = []
    for token in query_tokens:
        postings = index.postings.get(token)
        if not postings:
            return []
        sorted_lists.append(sorted(postings.keys()))

    pointers = [0] * len(sorted_lists)
    matches: list[int] = []

    while all(pointers[i] < len(sorted_lists[i]) for i in range(len(sorted_lists))):
        currents = [sorted_lists[i][pointers[i]] for i in range(len(sorted_lists))]
        max_doc = max(currents)
        if all(c == max_doc for c in currents):
            matches.append(max_doc)
            for i in range(len(pointers)):
                pointers[i] += 1
        else:
            # Skip-ahead each lagging pointer to the first entry >= max_doc.
            for i in range(len(pointers)):
                if sorted_lists[i][pointers[i]] < max_doc:
                    pointers[i] = _advance_pointer(sorted_lists[i], pointers[i], max_doc)

    return matches


def conjunctive_retrieval(
    index: Index,
    query_tokens: list[str],
    ranker: Ranker,
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """AND-filter then score and rank.

    The brief's ``find good friends`` example expects conjunctive
    semantics ("all pages containing the words"). This function
    composes Lecture 13's conjunctive intersection — using the
    skip-pointer optimised variant for production scale — with
    DAAT-style scoring on the surviving candidates.

    Args:
        index: The inverted index.
        query_tokens: Lowercased query tokens.
        ranker: Scoring strategy implementing the Ranker protocol.
        top_k: Maximum results to return; ``None`` returns every match.

    Returns:
        ``(doc_id, score)`` tuples sorted by score descending; ties on
        score break on doc_id ascending.
    """
    matching_ids = conjunctive_match_with_skip(index, query_tokens)
    if not matching_ids:
        return []

    scored = [
        (doc_id, ranker.score(index, query_tokens, doc_id))
        for doc_id in matching_ids
    ]
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    if top_k is not None:
        scored = scored[:top_k]
    return scored


def phrase_match(
    index: Index,
    query_tokens: list[str],
) -> list[int]:
    """Return doc_ids where ``query_tokens`` form a consecutive phrase.

    A phrase ``[t_0, t_1, ..., t_{n-1}]`` occurs starting at position
    ``p`` in a document iff every ``t_i`` is at position ``p + i``.
    Equivalently, after subtracting each token's offset ``i`` from its
    position list, the N normalised lists must share at least one
    common value — that shared value is exactly ``p``. Computing the
    set intersection of the normalised lists therefore answers the
    phrase question in linear time per candidate.

    :func:`conjunctive_match` runs first as a cheap prefilter: a phrase
    match implies every term is present in the document, so the AND
    filter eliminates obvious non-candidates without touching positions.

    Known limitation: positions are global offsets within the body's
    flattened text. Our parser concatenates structural fields with
    whitespace separators, so a phrase that straddles a structural
    boundary (e.g. one ``<div class="quote">``'s last token followed
    by the next quote's first token) can spuriously match. The
    coursework target site rarely surfaces this in practice; a full
    fix requires the indexer to interleave phrase-boundary markers.
    """
    if not query_tokens:
        return []

    candidates = conjunctive_match(index, query_tokens)
    if not candidates:
        return []

    matching: list[int] = []
    for doc_id in candidates:
        normalised: list[set[int]] = []
        for offset, token in enumerate(query_tokens):
            posting = index.postings[token][doc_id]
            raw_positions = posting.get("positions", [])
            if not isinstance(raw_positions, list):
                normalised.append(set())
                continue
            # Drop positions that would imply the phrase starting
            # before index 0 — they cannot align with a valid offset.
            normalised.append({p - offset for p in raw_positions if p >= offset})

        if normalised and set.intersection(*normalised):
            matching.append(doc_id)

    return matching


def phrase_retrieval(
    index: Index,
    query_tokens: list[str],
    ranker: Ranker,
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """Filter to phrase matches then score and rank them.

    Same composition pattern as :func:`conjunctive_retrieval`, but
    swaps the prefilter for the stricter :func:`phrase_match`. Only
    documents containing the query as a consecutive phrase survive to
    the scoring stage.
    """
    matching_ids = phrase_match(index, query_tokens)
    if not matching_ids:
        return []

    scored = [
        (doc_id, ranker.score(index, query_tokens, doc_id))
        for doc_id in matching_ids
    ]
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    if top_k is not None:
        scored = scored[:top_k]
    return scored
