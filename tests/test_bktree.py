"""Tests for the BK-tree metric index (Burkhard & Keller 1973)."""

from __future__ import annotations

import random
import unittest

from src.bktree import BKTree
from src.suggest import levenshtein_distance


def _linear_scan(
    target: str,
    vocabulary: list[str],
    max_distance: int,
) -> list[tuple[int, str]]:
    """Reference implementation: brute-force scan.

    BK-tree search results MUST match this output exactly (same
    items, same order) for every input — that is the equivalence
    invariant the property tests below pin down. Mirrors the
    Lecture-13 ``conjunctive_match`` / ``conjunctive_match_with_skip``
    pairing pattern this project already uses.
    """
    scored = [
        (levenshtein_distance(target, term), term) for term in vocabulary
    ]
    within = [pair for pair in scored if pair[0] <= max_distance]
    within.sort(key=lambda p: (p[0], p[1]))
    return within


class BKTreeShapeTests(unittest.TestCase):
    def test_empty_tree_has_length_zero(self):
        tree = BKTree(levenshtein_distance)
        self.assertEqual(len(tree), 0)

    def test_search_on_empty_tree_returns_empty_list(self):
        tree = BKTree(levenshtein_distance)
        self.assertEqual(tree.search("anything", max_distance=2), [])

    def test_single_term_tree_finds_self_at_distance_zero(self):
        tree = BKTree(levenshtein_distance, ["wisdom"])
        self.assertEqual(tree.search("wisdom", max_distance=0), [(0, "wisdom")])

    def test_single_term_tree_returns_empty_when_target_too_far(self):
        tree = BKTree(levenshtein_distance, ["wisdom"])
        # "knowledge" is far from "wisdom" — exceeds threshold 2.
        self.assertEqual(tree.search("knowledge", max_distance=2), [])

    def test_duplicate_add_is_idempotent(self):
        tree = BKTree(levenshtein_distance)
        tree.add("wisdom")
        tree.add("wisdom")
        tree.add("wisdom")
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree.search("wisdom", max_distance=0), [(0, "wisdom")])

    def test_construction_from_iterable_equivalent_to_incremental_add(self):
        terms = ["wisdom", "friend", "indifference", "good", "knowledge"]
        bulk = BKTree(levenshtein_distance, terms)
        incremental = BKTree(levenshtein_distance)
        for t in terms:
            incremental.add(t)

        # Both trees must support the same queries. We don't compare
        # internal shapes — those depend on insertion order — only
        # observable search results.
        for target in ("wsdom", "frend", "knowlege"):
            self.assertEqual(
                bulk.search(target, max_distance=2),
                incremental.search(target, max_distance=2),
            )


class BKTreeSearchTests(unittest.TestCase):
    VOCABULARY = [
        "wisdom",
        "wisdoms",
        "kingdom",
        "freedom",
        "friend",
        "friendly",
        "friends",
        "indifference",
        "indignant",
        "good",
        "goodness",
        "great",
    ]

    def setUp(self):
        self.tree = BKTree(levenshtein_distance, self.VOCABULARY)

    def test_threshold_zero_returns_only_exact_match(self):
        # Threshold 0 makes the BK-tree behave as an exact-membership
        # check — anchors the corner case where pruning eliminates
        # every off-edge subtree.
        self.assertEqual(self.tree.search("friend", max_distance=0), [(0, "friend")])
        self.assertEqual(self.tree.search("missing", max_distance=0), [])

    def test_close_typo_is_found(self):
        # One missing 'f' — distance 1 from "indifference".
        results = self.tree.search("indiference", max_distance=2)
        self.assertIn((1, "indifference"), results)

    def test_results_sorted_by_distance_then_alpha(self):
        # Match contract of suggest_corrections: distance ascending,
        # alpha within tied distance. The CLI relies on this for the
        # "Did you mean: <top candidate>?" reformulation.
        results = self.tree.search("friend", max_distance=2)
        # ``friend`` itself at distance 0, plus the close neighbours
        # at distance 1 / 2.
        self.assertEqual(results[0], (0, "friend"))
        # Within a distance bucket, alpha ordering.
        for i in range(1, len(results)):
            d_prev, t_prev = results[i - 1]
            d_curr, t_curr = results[i]
            self.assertLessEqual(d_prev, d_curr)
            if d_prev == d_curr:
                self.assertLessEqual(t_prev, t_curr)

    def test_large_threshold_returns_every_term(self):
        # Threshold of 100 is well above any reasonable Levenshtein
        # distance between English words. Every term must appear,
        # which doubles as a sanity check that pruning is sound (no
        # false negatives via aggressive triangle-inequality cuts).
        results = self.tree.search("query", max_distance=100)
        returned = {term for _, term in results}
        self.assertEqual(returned, set(self.VOCABULARY))

    def test_word_boundary_substring_does_not_match(self):
        # "good" is in the vocabulary; "goodness" too. A search for
        # "good" with threshold 0 should return only "good", not the
        # substring of "goodness". Pins that distance comparison is
        # by full term, not substring.
        self.assertEqual(self.tree.search("good", max_distance=0), [(0, "good")])

    def test_rejects_negative_threshold(self):
        with self.assertRaises(ValueError):
            self.tree.search("friend", max_distance=-1)


class BKTreeEquivalenceTests(unittest.TestCase):
    """Property-based: BK-tree search MUST equal linear scan output.

    This is the invariant that makes BK-tree a drop-in optimisation
    rather than a behaviour change. Mirrors the
    ``conjunctive_match`` / ``conjunctive_match_with_skip`` property
    test that pins the v1.0.0 skip-pointer optimisation.
    """

    def test_random_vocabulary_search_matches_linear_scan(self):
        rng = random.Random(20260512)
        alphabet = "abcdef"
        vocabulary = list({
            "".join(rng.choices(alphabet, k=rng.randint(1, 6)))
            for _ in range(60)
        })
        tree = BKTree(levenshtein_distance, vocabulary)

        # 20 random targets × every threshold in {0, 1, 2, 3}.
        for _ in range(20):
            target = "".join(rng.choices(alphabet, k=rng.randint(1, 8)))
            for threshold in (0, 1, 2, 3):
                self.assertEqual(
                    tree.search(target, max_distance=threshold),
                    _linear_scan(target, vocabulary, threshold),
                    f"divergence on target={target!r}, threshold={threshold}",
                )

    def test_insertion_order_independence(self):
        # The tree's internal shape depends on insertion order, but
        # search results must not. Two trees built from the same
        # vocabulary in different orders must answer every query
        # identically.
        terms = [
            "alpha", "beta", "gamma", "delta", "epsilon",
            "zeta", "eta", "theta", "iota", "kappa",
        ]
        forward = BKTree(levenshtein_distance, terms)
        reverse = BKTree(levenshtein_distance, list(reversed(terms)))
        shuffled = BKTree(
            levenshtein_distance,
            sorted(terms, key=lambda t: hash((t, 42)) & 0xFFFF),
        )

        for target in ("alpha", "alfa", "phi", "beta", "delt"):
            for threshold in (0, 1, 2):
                expected = _linear_scan(target, terms, threshold)
                self.assertEqual(
                    forward.search(target, max_distance=threshold), expected
                )
                self.assertEqual(
                    reverse.search(target, max_distance=threshold), expected
                )
                self.assertEqual(
                    shuffled.search(target, max_distance=threshold), expected
                )


if __name__ == "__main__":
    unittest.main()
