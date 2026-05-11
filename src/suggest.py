"""Spelling-correction utilities for the search CLI.

Implements the Levenshtein (edit) distance and a vocabulary-based
suggestion function used by the ``find`` command to produce
"Did you mean..." prompts when a query returns no results.

References:
* Wagner & Fischer (1974), "The String-to-String Correction Problem"
  — the dynamic-programming formulation used in :func:`levenshtein_distance`.
* Manning, Raghavan & Schutze, *Introduction to Information Retrieval*,
  Chapter 3 "Dictionaries and tolerant retrieval" — motivates spelling
  correction over a posting-list vocabulary as a standard IR feature.

The distance function uses the textbook O(|s1| x |s2|) dynamic
program with a space optimisation: only the current and previous DP
rows are held in memory at any time, giving O(min(|s1|, |s2|)) space.
This is enough for query-time correction over vocabularies of a few
thousand terms — a tighter algorithm (BK-tree, n-gram filtering) is
overkill at this scale and is queued for v1.6.0 if the corpus grows
beyond what a linear scan handles comfortably.
"""

from __future__ import annotations

from typing import Iterable


def levenshtein_distance(s1: str, s2: str) -> int:
    """Return the edit distance between ``s1`` and ``s2``.

    Edits counted: single-character insertions, deletions, and
    substitutions, each costing 1. Transpositions (Damerau-Levenshtein)
    are *not* a single edit — ``"ab" -> "ba"`` costs 2 here.

    The implementation uses Wagner-Fischer dynamic programming with
    a rolling two-row buffer:

    * ``previous[j]`` = distance between ``s1[:i-1]`` and ``s2[:j]``
    * ``current[j]``  = distance between ``s1[:i]``   and ``s2[:j]``

    so each cell is computed from one cell up (``previous[j]``), one
    cell left (``current[j-1]``), and one cell up-and-left
    (``previous[j-1]``). Holding only the two rows brings memory from
    O(|s1| x |s2|) to O(|s2|) without changing the result.

    Args:
        s1: Source string.
        s2: Target string.

    Returns:
        Non-negative integer edit distance.

    Examples:
        >>> levenshtein_distance("kitten", "sitting")
        3
        >>> levenshtein_distance("", "abc")
        3
        >>> levenshtein_distance("abc", "abc")
        0
    """
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    # Make ``s2`` the shorter row to minimise inner-loop allocation.
    # Swapping does not change the symmetric edit distance.
    if len(s2) > len(s1):
        s1, s2 = s2, s1

    # previous row corresponds to "i = 0" (empty prefix of s1): distance
    # is just the length of the s2 prefix.
    previous = list(range(len(s2) + 1))
    current = [0] * (len(s2) + 1)

    for i, ch1 in enumerate(s1, start=1):
        current[0] = i  # distance from s1[:i] to empty s2
        for j, ch2 in enumerate(s2, start=1):
            cost_substitute = previous[j - 1] + (0 if ch1 == ch2 else 1)
            cost_delete = previous[j] + 1
            cost_insert = current[j - 1] + 1
            current[j] = min(cost_substitute, cost_delete, cost_insert)
        previous, current = current, previous

    return previous[len(s2)]


def suggest_corrections(
    query_tokens: Iterable[str],
    vocabulary: Iterable[str],
    *,
    max_distance: int = 2,
    max_suggestions: int = 3,
) -> dict[str, list[str]]:
    """Suggest vocabulary terms close to each unknown query token.

    For each token in ``query_tokens`` that does *not* appear in
    ``vocabulary``, return the closest vocabulary terms by Levenshtein
    distance, capped at ``max_distance`` edits and at most
    ``max_suggestions`` results per unknown token. Tokens that *are*
    in the vocabulary are omitted from the result entirely — the
    caller only cares about probable typos.

    The suggestions for each token are sorted primarily by distance
    ascending, secondarily by the term itself ascending, so the order
    is deterministic across runs and platforms.

    Args:
        query_tokens: Tokens the user submitted, lowercased by the
            caller (the tokeniser already does this for index queries).
        vocabulary: All terms present in the index (typically
            ``index.postings.keys()``).
        max_distance: Maximum edit distance to consider. The IR
            convention (Manning et al., Ch. 3) is 1 for tight
            corrections, 2 for forgiving ones; 2 catches most
            real-world single-finger typos without ballooning the
            candidate set.
        max_suggestions: Cap on suggestions returned per unknown
            token. Three keeps the CLI prompt readable.

    Returns:
        Mapping ``{unknown_token: [candidate_1, candidate_2, ...]}``.
        Tokens with no candidates within ``max_distance`` are included
        with an empty list — the caller distinguishes "no suggestion"
        from "this token is fine".
    """
    if max_distance < 0:
        raise ValueError(f"max_distance must be non-negative, got {max_distance}")
    if max_suggestions < 1:
        raise ValueError(f"max_suggestions must be positive, got {max_suggestions}")

    # Materialise once; the caller might pass a generator and we need
    # to iterate it per unknown token.
    vocab_list = list(vocabulary)
    vocab_set = set(vocab_list)

    suggestions: dict[str, list[str]] = {}
    for token in query_tokens:
        if token in vocab_set:
            # Token is known; not a typo candidate — skip entirely so
            # the CLI does not surface "Did you mean: <synonyms>?" for
            # legitimate but rare queries.
            continue
        scored: list[tuple[int, str]] = []
        for term in vocab_list:
            # Cheap length-difference prune — if |len(token) - len(term)|
            # already exceeds max_distance, no edit script of cost
            # <= max_distance can bridge them. Saves ~half the DP work
            # on a typical English vocabulary.
            if abs(len(token) - len(term)) > max_distance:
                continue
            d = levenshtein_distance(token, term)
            if d <= max_distance:
                scored.append((d, term))
        scored.sort(key=lambda pair: (pair[0], pair[1]))
        suggestions[token] = [term for _, term in scored[:max_suggestions]]

    return suggestions
