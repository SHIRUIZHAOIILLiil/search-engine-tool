"""Tests for spelling-correction utilities (Levenshtein + suggestion)."""

from __future__ import annotations

import random
import unittest

from src.suggest import levenshtein_distance, suggest_corrections


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


if __name__ == "__main__":
    unittest.main()
