"""BK-tree metric index for sub-linear edit-distance lookup.

Burkhard & Keller (1973), "Some approaches to best-match file
searching", *CACM*. Manning, Raghavan & Schutze, *Introduction to
Information Retrieval* (Ch. 3.3) covers it as the standard data
structure for spelling correction over an indexed vocabulary.

A BK-tree exploits the **triangle inequality** that any metric
satisfies — for the edit (Levenshtein) distance ``d``:

    | d(a, c) - d(b, c) |  <=  d(a, b)  <=  d(a, c) + d(b, c)

When the tree is built so that every edge from a node ``p`` to its
child ``c`` carries the label ``w = d(p, c)``, a search for terms
within distance ``k`` of a target ``t`` can prune any child subtree
rooted at ``c`` for which::

    | w - d(t, p) |  >  k

because the inequality above guarantees no descendant of ``c`` is
within distance ``k`` of ``t`` either. In practice this prunes
roughly a logarithmic fraction of the tree per query — search cost
goes from O(N) (the linear scan in :mod:`src.suggest`) to expected
O(log N) on natural-language vocabularies.

Design notes:

* The distance function is **injected** at construction time so the
  tree stays a generic metric structure. Pairing with a non-metric
  distance (e.g. a simple substring test that violates triangle
  inequality) would silently produce wrong results.
* :meth:`BKTree.add` is **idempotent** — adding the same term twice
  leaves the tree unchanged so callers can replay an insertion log
  without bookkeeping.
* The tree is not persisted — it is cheap to rebuild from the
  index's vocabulary and storing it on disk would complicate the
  ``INDEX_VERSION`` story without value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class _Node:
    """One vocabulary term plus its distance-keyed child subtrees."""

    term: str
    # children[distance_to_parent] = subtree root that lives at exactly
    # ``distance_to_parent`` edit operations away from ``self``. A dict
    # rather than a list because edge weights skip values when the
    # vocabulary has no terms at certain distances.
    children: dict[int, "_Node"] = field(default_factory=dict)


class BKTree:
    """Metric-tree index for fast edit-distance lookup.

    Construct with a distance function (typically
    :func:`src.suggest.levenshtein_distance`) and either an initial
    vocabulary iterable or by calling :meth:`add` incrementally.
    Query via :meth:`search` with a target string and a distance
    threshold.

    The tree's correctness invariants are:

    1. Every edge from a node ``p`` to its child ``c`` is labelled
       with the exact distance ``self._distance(p.term, c.term)``.
    2. Within a single parent, every edge has a distinct label —
       this is what makes :meth:`add` deterministic without needing
       to track insertion order.
    3. The triangle-inequality pruning in :meth:`search` is sound
       *only* if ``distance`` actually satisfies the metric axioms.
       Levenshtein does. Hamming distance, longest-common-subsequence
       distance, and Damerau-Levenshtein also do. Plain substring
       containment does not — do not use it here.
    """

    def __init__(
        self,
        distance: Callable[[str, str], int],
        vocabulary: list[str] | None = None,
    ) -> None:
        self._distance = distance
        self._root: _Node | None = None
        if vocabulary:
            for term in vocabulary:
                self.add(term)

    def __len__(self) -> int:
        return self._count_nodes(self._root)

    def _count_nodes(self, node: _Node | None) -> int:
        if node is None:
            return 0
        return 1 + sum(self._count_nodes(child) for child in node.children.values())

    def add(self, term: str) -> None:
        """Insert ``term`` into the tree.

        Walks from the root computing the distance to each node along
        the way. At each node the new term is either:

        * already present in a child subtree (recurse), or
        * absent (a fresh child gets created at the matching edge
          weight).

        Idempotent: re-adding an existing term is a no-op because
        every walk converges on its current position with distance 0
        somewhere on the path.
        """
        if self._root is None:
            self._root = _Node(term=term)
            return

        current = self._root
        while True:
            d = self._distance(term, current.term)
            if d == 0:
                # The term is already in the tree; do not duplicate.
                return
            existing_child = current.children.get(d)
            if existing_child is None:
                current.children[d] = _Node(term=term)
                return
            current = existing_child

    def search(self, target: str, max_distance: int) -> list[tuple[int, str]]:
        """Return ``(distance, term)`` for every term within ``max_distance``.

        The returned list is sorted by ``(distance, term)`` ascending,
        matching the contract of the linear-scan
        :func:`src.suggest.suggest_corrections` so the two
        implementations are drop-in interchangeable. An empty list
        means no term in the vocabulary is within ``max_distance``
        edits of ``target``.

        Implementation walks a DFS stack rather than Python recursion
        to avoid hitting the interpreter's recursion limit on very
        long, narrow trees (worst case for nearly-unique vocabularies).
        """
        if max_distance < 0:
            raise ValueError(f"max_distance must be non-negative, got {max_distance}")
        if self._root is None:
            return []

        results: list[tuple[int, str]] = []
        stack: list[_Node] = [self._root]
        while stack:
            node = stack.pop()
            d_to_node = self._distance(target, node.term)
            if d_to_node <= max_distance:
                results.append((d_to_node, node.term))

            # Triangle-inequality prune: any child reachable from
            # ``node`` along an edge of weight ``w`` can be at most
            # ``w + d_to_node`` from the target and at least
            # ``|w - d_to_node|``. So if either bound forbids
            # being within ``max_distance``, the whole subtree
            # cannot contribute and is skipped.
            lo = d_to_node - max_distance
            hi = d_to_node + max_distance
            for edge_weight, child in node.children.items():
                if lo <= edge_weight <= hi:
                    stack.append(child)

        results.sort(key=lambda pair: (pair[0], pair[1]))
        return results
