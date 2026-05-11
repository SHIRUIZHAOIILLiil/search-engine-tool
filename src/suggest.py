"""Spelling-correction utilities for the search CLI.

Implements the Levenshtein (edit) distance and a vocabulary-based
suggestion function used by the ``find`` command to produce
"Did you mean..." prompts when a query returns no results.

References:
* Wagner & Fischer (1974), "The String-to-String Correction Problem"
  — the dynamic-programming formulation used in :func:`levenshtein_distance`.
* Burkhard & Keller (1973), "Some approaches to best-match file
  searching", *CACM* — the BK-tree used to accelerate large-vocabulary
  lookup; see :mod:`src.bktree`.
* Manning, Raghavan & Schutze, *Introduction to Information Retrieval*,
  Chapter 3 "Dictionaries and tolerant retrieval" — motivates spelling
  correction over a posting-list vocabulary as a standard IR feature
  and covers BK-trees as the textbook acceleration.

The distance function uses the textbook O(|s1| x |s2|) dynamic
program with a space optimisation: only the current and previous DP
rows are held in memory at any time, giving O(min(|s1|, |s2|)) space.

:func:`suggest_corrections` adapts to vocabulary size: a small
vocabulary (under :data:`BKTREE_MIN_VOCAB` terms) uses the
length-pruned linear scan, while a large vocabulary switches to a
BK-tree built on the fly. Both paths are provably equivalent — a
property test in ``tests/test_suggest.py`` pins their output set
across randomised inputs.
"""

from __future__ import annotations

from typing import Iterable

from src.bktree import BKTree

# Vocabulary size at which the BK-tree path becomes cheaper than
# linear scan. Below this the BK-tree's build cost (one full pass
# over the vocab to insert nodes) is not amortised by the savings
# on the query pass, so the simpler scan wins. The threshold was
# settled at 500 based on the v1.1.0 benchmark methodology: a
# synthetic 500-term vocab is the smallest size where the build
# cost ceases to dominate a single-token query under default
# parameters.
BKTREE_MIN_VOCAB = 500


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
    bktree: BKTree | None = None,
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

    The function adapts to the vocabulary size: small vocabularies
    take the length-pruned linear scan; vocabularies of
    :data:`BKTREE_MIN_VOCAB` terms or more switch to a BK-tree built
    on the fly (Burkhard & Keller 1973). Callers that issue many
    successive queries against the same vocabulary should pass a
    pre-built :class:`~src.bktree.BKTree` via ``bktree`` to amortise
    the build cost across calls — that path is what :mod:`src.search`
    wires up so the ``Did you mean`` hint stays cheap even on the
    largest corpora.

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
        bktree: Optional pre-built BK-tree over ``vocabulary``.
            When supplied, replaces both the linear scan and the
            on-the-fly BK-tree build. The caller is responsible for
            keeping it in sync with ``vocabulary`` — a mismatch
            silently produces wrong suggestions.

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

    # Materialise the vocabulary once; the caller may pass a generator
    # and both paths below need to iterate it (linear scan) or membership
    # test (every path).
    vocab_list = list(vocabulary)
    vocab_set = set(vocab_list)
    tokens_list = list(query_tokens)

    if bktree is None and len(vocab_list) >= BKTREE_MIN_VOCAB:
        # Large-vocabulary path: build a BK-tree once and query it
        # for every unknown token in this call. Build cost is
        # amortised over query_tokens; for the typical 1-3 token
        # query this is already cheaper than the linear scan once
        # the vocab passes the threshold.
        bktree = BKTree(levenshtein_distance, vocab_list)

    if bktree is not None:
        return _suggest_via_bktree(
            tokens_list, vocab_set, bktree,
            max_distance=max_distance,
            max_suggestions=max_suggestions,
        )
    return _suggest_via_linear_scan(
        tokens_list, vocab_list, vocab_set,
        max_distance=max_distance,
        max_suggestions=max_suggestions,
    )


def _suggest_via_linear_scan(
    query_tokens: list[str],
    vocab_list: list[str],
    vocab_set: set[str],
    *,
    max_distance: int,
    max_suggestions: int,
) -> dict[str, list[str]]:
    """Brute-force scan with a length-difference prune.

    Preserved alongside the BK-tree path as the reference
    implementation — the property test in ``tests/test_suggest.py``
    pins both paths to the same output set, so divergence in either
    direction surfaces immediately. This is the same dual-impl
    pattern that the conjunctive-match family uses (simple vs
    skip-pointer in v1.0.0).
    """
    suggestions: dict[str, list[str]] = {}
    for token in query_tokens:
        if token in vocab_set:
            continue
        scored: list[tuple[int, str]] = []
        for term in vocab_list:
            # Length-difference prune: ``|len(token) - len(term)| > k``
            # implies edit distance > k for any costless transformation.
            if abs(len(token) - len(term)) > max_distance:
                continue
            d = levenshtein_distance(token, term)
            if d <= max_distance:
                scored.append((d, term))
        scored.sort(key=lambda pair: (pair[0], pair[1]))
        suggestions[token] = [term for _, term in scored[:max_suggestions]]
    return suggestions


def _suggest_via_bktree(
    query_tokens: list[str],
    vocab_set: set[str],
    tree: BKTree,
    *,
    max_distance: int,
    max_suggestions: int,
) -> dict[str, list[str]]:
    """BK-tree path: O(log N) expected per query token.

    The BK-tree returns candidates already sorted by
    ``(distance, term)`` so the caller's slicing in ``[:max_suggestions]``
    keeps the closest matches. ``vocab_set`` is consulted only to
    skip known tokens — exact-match short-circuit, same as the
    linear scan.
    """
    suggestions: dict[str, list[str]] = {}
    for token in query_tokens:
        if token in vocab_set:
            continue
        scored = tree.search(token, max_distance=max_distance)
        suggestions[token] = [term for _, term in scored[:max_suggestions]]
    return suggestions
