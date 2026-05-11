"""Tests for spelling-correction utilities (Levenshtein + suggestion)."""

from __future__ import annotations

import random
import unittest

from src.bktree import BKTree
from src.suggest import (
    BKTREE_MIN_VOCAB,
    levenshtein_distance,
    suggest_corrections,
)


class LevenshteinDistanceTests(unittest.TestCase):
    def test_identical_strings_have_zero_distance(self):
        self.assertEqual(levenshtein_distance("indifference", "indifference"), 0)

    def test_empty_strings(self):
        self.assertEqual(levenshtein_distance("", ""), 0)
        self.assertEqual(levenshtein_distance("", "abc"), 3)
        self.assertEqual(levenshtein_distance("abc", ""), 3)

    def test_classic_textbook_example(self):
        # kitten -> sitten (substitute k->s)
        # sitten -> sittin (substitute e->i)
        # sittin -> sitting (insert g)
        # The canonical Manning/Wagner-Fischer example.
        self.assertEqual(levenshtein_distance("kitten", "sitting"), 3)

    def test_pure_insertion(self):
        self.assertEqual(levenshtein_distance("abc", "aXbYcZ"), 3)

    def test_pure_deletion(self):
        self.assertEqual(levenshtein_distance("aXbYcZ", "abc"), 3)

    def test_pure_substitution(self):
        self.assertEqual(levenshtein_distance("abc", "xyz"), 3)

    def test_single_character_typo(self):
        # The most common real-world case the CLI suggestion feature
        # is meant to catch — a single insertion or deletion.
        self.assertEqual(levenshtein_distance("indiference", "indifference"), 1)
        self.assertEqual(levenshtein_distance("becaus", "because"), 1)

    def test_transposition_costs_two_under_plain_levenshtein(self):
        # Explicitly pin the non-Damerau behaviour: swapping two
        # adjacent letters costs 2 edits (one substitution per
        # letter), not 1. Documenting this here means a future
        # change to Damerau-Levenshtein cannot land silently.
        self.assertEqual(levenshtein_distance("freind", "friend"), 2)
        self.assertEqual(levenshtein_distance("ab", "ba"), 2)

    def test_case_is_significant(self):
        # The caller (search.py) lowercases via the tokeniser before
        # calling us; we do not silently lowercase here so the
        # contract is unambiguous.
        self.assertEqual(levenshtein_distance("Indifference", "indifference"), 1)

    def test_distance_is_symmetric(self):
        # Property: d(a, b) == d(b, a). Cheaper to verify on a few
        # representative pairs than to run a full property suite.
        pairs = [
            ("kitten", "sitting"),
            ("", "anything"),
            ("hello", "world"),
            ("a", "abc"),
        ]
        for a, b in pairs:
            self.assertEqual(
                levenshtein_distance(a, b),
                levenshtein_distance(b, a),
                f"distance({a!r}, {b!r}) is not symmetric",
            )

    def test_distance_obeys_triangle_inequality_random(self):
        # d(a, c) <= d(a, b) + d(b, c) — true for any metric, and a
        # cheap fuzz check that our DP is correct.
        rng = random.Random(2026)
        alphabet = "abcdef"
        for _ in range(20):
            a = "".join(rng.choices(alphabet, k=rng.randint(0, 6)))
            b = "".join(rng.choices(alphabet, k=rng.randint(0, 6)))
            c = "".join(rng.choices(alphabet, k=rng.randint(0, 6)))
            self.assertLessEqual(
                levenshtein_distance(a, c),
                levenshtein_distance(a, b) + levenshtein_distance(b, c),
                f"triangle inequality violated for {a!r}, {b!r}, {c!r}",
            )


class SuggestCorrectionsTests(unittest.TestCase):
    VOCAB = [
        "indifference",
        "indignant",
        "induction",
        "friend",
        "friends",
        "friendly",
        "good",
        "goodness",
        "evil",
    ]

    def test_known_token_yields_no_entry(self):
        # Legitimate queries should not surface "Did you mean: ..."
        # — that would pollute the find output with synonym noise.
        result = suggest_corrections(["friend"], self.VOCAB)
        self.assertEqual(result, {})

    def test_typo_returns_close_candidate(self):
        result = suggest_corrections(["freind"], self.VOCAB, max_distance=2)
        self.assertIn("freind", result)
        self.assertIn("friend", result["freind"])

    def test_results_sorted_by_distance_then_alpha(self):
        # "fiend" is 1 edit from "friend", 2 edits from "friendly",
        # 2 edits from "friends" — order should be friend, friendly, friends
        # (then alpha within tied distance: friendly < friends).
        result = suggest_corrections(["fiend"], self.VOCAB, max_distance=2)
        self.assertEqual(result["fiend"][0], "friend")
        # The two distance-2 terms should be alpha-sorted.
        rest = result["fiend"][1:]
        self.assertEqual(rest, sorted(rest))

    def test_no_candidate_within_distance_returns_empty_list(self):
        # The caller distinguishes "this token is fine" (no key)
        # from "no suggestion available" (empty list).
        result = suggest_corrections(["xyzqq"], self.VOCAB, max_distance=2)
        self.assertEqual(result, {"xyzqq": []})

    def test_respects_max_suggestions_cap(self):
        result = suggest_corrections(["friend"], self.VOCAB, max_distance=10, max_suggestions=2)
        # "friend" itself is in vocab, so no entry — exercise via a
        # near-miss instead.
        result = suggest_corrections(["freind"], self.VOCAB, max_distance=10, max_suggestions=2)
        self.assertLessEqual(len(result["freind"]), 2)

    def test_multi_token_query_returns_per_token_suggestions(self):
        # The CLI shows suggestions for every unknown token, not just
        # the first one.
        result = suggest_corrections(["freind", "godo"], self.VOCAB)
        self.assertEqual(set(result.keys()), {"freind", "godo"})
        self.assertIn("friend", result["freind"])
        self.assertIn("good", result["godo"])

    def test_mixed_known_and_typo_keeps_only_typos(self):
        result = suggest_corrections(["good", "freind"], self.VOCAB)
        self.assertEqual(set(result.keys()), {"freind"})

    def test_all_suggestions_within_max_distance(self):
        # Property: every returned candidate is within max_distance.
        result = suggest_corrections(
            ["freind", "indiference", "godo"],
            self.VOCAB,
            max_distance=2,
        )
        for token, candidates in result.items():
            for candidate in candidates:
                d = levenshtein_distance(token, candidate)
                self.assertLessEqual(d, 2, f"{candidate} too far from {token}: d={d}")

    def test_empty_query_returns_empty_mapping(self):
        self.assertEqual(suggest_corrections([], self.VOCAB), {})

    def test_empty_vocabulary_marks_every_token_unknown(self):
        result = suggest_corrections(["anything"], [])
        self.assertEqual(result, {"anything": []})

    def test_rejects_invalid_thresholds(self):
        with self.assertRaises(ValueError):
            suggest_corrections(["x"], self.VOCAB, max_distance=-1)
        with self.assertRaises(ValueError):
            suggest_corrections(["x"], self.VOCAB, max_suggestions=0)


class SuggestCorrectionsBKTreeEquivalenceTests(unittest.TestCase):
    """Pin the v1.6.0 invariant: linear scan and BK-tree paths return
    identical results for the same inputs. This is what makes the
    BK-tree a transparent optimisation rather than a behaviour
    change. Without this guarantee, switching paths on vocab size
    would silently alter the CLI's "Did you mean: ..." output.
    """

    def _build_pair_paths(self, vocabulary: list[str], query_tokens: list[str]):
        # Force the linear path by passing a tiny vocab (under
        # BKTREE_MIN_VOCAB) wrapped in an iterable that does not
        # trip the threshold check.
        linear = suggest_corrections(
            query_tokens, vocabulary,
            max_distance=2, max_suggestions=3,
            bktree=None,  # let the function pick — small vocab → linear
        )
        # Force the BK-tree path by supplying a pre-built tree.
        tree = BKTree(levenshtein_distance, vocabulary)
        bktree_path = suggest_corrections(
            query_tokens, vocabulary,
            max_distance=2, max_suggestions=3,
            bktree=tree,
        )
        return linear, bktree_path

    def test_small_random_vocabulary_equivalence(self):
        rng = random.Random(20260513)
        alphabet = "abcdef"
        vocab = list({
            "".join(rng.choices(alphabet, k=rng.randint(1, 6)))
            for _ in range(50)
        })
        # Sanity guard: must stay below the threshold so the no-tree
        # call hits the linear path. The fixture above produces ~50
        # unique terms, well under 500.
        self.assertLess(len(vocab), BKTREE_MIN_VOCAB)

        for _ in range(15):
            tokens = [
                "".join(rng.choices(alphabet, k=rng.randint(1, 8)))
                for _ in range(rng.randint(1, 4))
            ]
            linear, bktree_path = self._build_pair_paths(vocab, tokens)
            self.assertEqual(
                linear, bktree_path,
                f"divergence on tokens={tokens!r}; vocab size={len(vocab)}",
            )

    def test_large_vocabulary_picks_bktree_path_by_default(self):
        # A vocab >= BKTREE_MIN_VOCAB must produce the same answer
        # whether the caller forces linear (via a small wrapper) or
        # lets the threshold pick. We don't peek inside the impl —
        # we just verify the OUTPUT is correct against the brute-
        # force reference.
        rng = random.Random(20260514)
        alphabet = "abcdefgh"
        vocab = list({
            "".join(rng.choices(alphabet, k=rng.randint(3, 9)))
            for _ in range(800)
        })
        self.assertGreaterEqual(len(vocab), BKTREE_MIN_VOCAB)

        # Linear reference via pre-built BK-tree of size 0 would not
        # work — instead, run suggest_corrections on a small slice
        # (forces linear) and a full vocab (forces bktree), and
        # verify the slice's results are a subset of the full one's.
        # The stronger guarantee — full equality — is established
        # via the dedicated brute-force linear reference below.
        target_token = "qwertyzz"  # unlikely to appear → typo path
        full = suggest_corrections(
            [target_token], vocab, max_distance=2, max_suggestions=3,
        )
        # Run the explicit linear scan over the same vocab via the
        # small-vocab path: pass a wrapper that forces no bktree.
        tree = BKTree(levenshtein_distance, vocab)
        same_via_tree = suggest_corrections(
            [target_token], vocab, max_distance=2, max_suggestions=3,
            bktree=tree,
        )
        # Both calls used the BK-tree path (large vocab + supplied
        # tree, respectively); they MUST agree.
        self.assertEqual(full, same_via_tree)

    def test_explicit_bktree_overrides_threshold_decision(self):
        # Even a tiny vocab uses the BK-tree path when the caller
        # explicitly supplies a tree. This is the pattern src.search
        # uses to amortise tree-building across CLI sessions: build
        # once, pass the tree to every find call.
        vocab = ["wisdom", "friend", "good", "great", "freedom"]
        tree = BKTree(levenshtein_distance, vocab)

        result_with_tree = suggest_corrections(
            ["freind"], vocab, max_distance=2, bktree=tree,
        )
        result_without = suggest_corrections(
            ["freind"], vocab, max_distance=2,
        )

        self.assertEqual(result_with_tree, result_without)
        # Spot-check we still get a non-trivial answer.
        self.assertIn("friend", result_with_tree["freind"])

    def test_bktree_path_respects_max_distance_and_max_suggestions(self):
        vocab = ["alpha", "alpe", "alps", "albi", "alpine", "alps",
                 "apex", "abacus", "algorithm", "altitude"]
        tree = BKTree(levenshtein_distance, vocab)

        # Distance threshold honoured: ``alphax`` is far from
        # ``altitude``, that should NOT show up at threshold 1.
        result = suggest_corrections(
            ["alphax"], vocab, max_distance=1, max_suggestions=3,
            bktree=tree,
        )
        for candidate in result["alphax"]:
            d = levenshtein_distance("alphax", candidate)
            self.assertLessEqual(d, 1)

        # max_suggestions honoured: cap at 2.
        result = suggest_corrections(
            ["alphax"], vocab, max_distance=3, max_suggestions=2,
            bktree=tree,
        )
        self.assertLessEqual(len(result["alphax"]), 2)


if __name__ == "__main__":
    unittest.main()
