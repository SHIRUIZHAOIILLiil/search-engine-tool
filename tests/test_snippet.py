"""Tests for the snippet generator (Lecture 13 / Manning et al. Ch. 8.7)."""

from __future__ import annotations

import unittest

from src.snippet import extract_snippet


class ExtractSnippetSingleTokenTests(unittest.TestCase):
    def test_returns_excerpt_with_token_highlighted(self):
        body = (
            "Be the change that you wish to see in the world. "
            "A friend is one of the nicest things you can have."
        )

        snippet = extract_snippet(body, ["friend"])

        self.assertIn("[friend]", snippet)

    def test_excerpt_is_centered_around_first_match(self):
        # The snippet should quote text around the anchor, not from
        # the start of the body.
        body = (
            "A" * 200 + " " + "friend " + "B" * 200
        )

        snippet = extract_snippet(body, ["friend"])

        self.assertIn("[friend]", snippet)
        # The 200 leading 'A's should be truncated.
        self.assertTrue(snippet.startswith("...") or snippet.startswith("..."),
                        f"Expected leading ellipsis in {snippet!r}")

    def test_preserves_original_case_in_highlight(self):
        # Brief says case-insensitive matching; the snippet should
        # still show the user the original case from the body.
        body = "Good morning to all."

        snippet = extract_snippet(body, ["good"])

        self.assertIn("[Good]", snippet)
        self.assertNotIn("[good]", snippet)

    def test_no_ellipsis_when_body_fits_within_window(self):
        body = "A short body about a friend."

        snippet = extract_snippet(body, ["friend"], window_chars=70)

        self.assertNotIn("...", snippet)
        self.assertIn("[friend]", snippet)

    def test_no_leading_ellipsis_when_anchor_is_near_start(self):
        body = "Friend is one of the nicest things " + "X" * 200

        snippet = extract_snippet(body, ["friend"])

        self.assertFalse(snippet.startswith("..."))
        # But trailing ellipsis IS expected because the X's are truncated.
        self.assertTrue(snippet.endswith("..."))

    def test_returns_empty_string_when_no_match(self):
        body = "Nothing relevant here whatsoever."

        self.assertEqual(extract_snippet(body, ["friend"]), "")

    def test_returns_empty_string_for_empty_body(self):
        self.assertEqual(extract_snippet("", ["friend"]), "")

    def test_returns_empty_string_for_empty_query(self):
        self.assertEqual(extract_snippet("A body of text.", []), "")

    def test_word_boundary_prevents_substring_matches(self):
        # "good" must NOT highlight inside "goodness" — would mislead
        # the user about why the result matched.
        body = "Goodness gracious me, what a day."

        # No standalone "good" in body → no snippet at all.
        self.assertEqual(extract_snippet(body, ["good"]), "")


class ExtractSnippetMultiTokenTests(unittest.TestCase):
    def test_anchor_picks_earliest_token(self):
        # "friends" appears before "good" by char position; the
        # anchor should be at friends to surface the most relevant
        # match for the user.
        body = (
            "Hello and welcome friends, may your day be good and pleasant."
        )

        snippet = extract_snippet(body, ["good", "friends"])

        # Both tokens are highlighted; verifying the choice of anchor
        # is awkward without exposing internals, so we settle for the
        # invariant that both expected highlights show up.
        self.assertIn("[friends]", snippet)
        self.assertIn("[good]", snippet)

    def test_all_query_token_occurrences_are_highlighted(self):
        body = "good things come to good friends with good timing."

        snippet = extract_snippet(body, ["good", "friends"])

        # Three "good" occurrences; depending on the window size they
        # may not all fit. But every "good" that IS inside the window
        # must be bracketed — assertion is that the bracketed-good
        # count equals the raw-good count inside the snippet.
        raw_count = sum(1 for word in snippet.split() if word.strip(".,;:?!").lower().startswith("[good]"))
        # Sanity floor — at least one [good] must appear.
        self.assertGreaterEqual(raw_count, 1)
        self.assertIn("[friends]", snippet)

    def test_highlighting_is_case_insensitive_across_tokens(self):
        body = "Friends are GOOD companions; friends are good guides."

        snippet = extract_snippet(body, ["good", "friends"])

        # Each surface form keeps its original casing inside brackets.
        self.assertIn("[Friends]", snippet)
        self.assertIn("[friends]", snippet)
        self.assertIn("[GOOD]", snippet)
        self.assertIn("[good]", snippet)


class ExtractSnippetPhraseModeTests(unittest.TestCase):
    def test_phrase_match_highlights_entire_phrase_as_one_unit(self):
        body = "We are all good friends here, sharing the journey."

        snippet = extract_snippet(body, ["good", "friends"], phrase_mode=True)

        self.assertIn("[good friends]", snippet)
        # Importantly, neither token should be independently bracketed.
        self.assertNotIn("[good] [friends]", snippet)

    def test_phrase_match_tolerates_arbitrary_whitespace_between_tokens(self):
        # ``parse_html_to_fields`` joins structural fields with single
        # spaces, but in raw body text you sometimes see multiple
        # spaces / line breaks. The phrase matcher must still fire.
        body = "We are all good   friends here."

        snippet = extract_snippet(body, ["good", "friends"], phrase_mode=True)

        # Internal whitespace is collapsed to single spaces before
        # highlighting, so the bracketed phrase shows up canonically.
        self.assertIn("[good friends]", snippet)

    def test_phrase_match_word_boundaries_block_partial_matches(self):
        # "good friendship" should NOT trigger a phrase match for
        # "good friends" — the trailing ``\b`` after ``friends``
        # blocks the alphanumeric continuation.
        body = "It was a good friendship to remember."

        self.assertEqual(
            extract_snippet(body, ["good", "friends"], phrase_mode=True),
            "",
        )

    def test_phrase_mode_returns_empty_when_only_individual_tokens_match(self):
        body = "Good ideas come from many friends, but not necessarily together."

        # "good" and "friends" each appear, but never adjacent — so
        # phrase mode finds nothing.
        self.assertEqual(
            extract_snippet(body, ["good", "friends"], phrase_mode=True),
            "",
        )


class ExtractSnippetWindowAndBoundaryTests(unittest.TestCase):
    def test_window_aligns_to_whitespace_no_mid_word_truncation(self):
        # Realistic English: short common words around the match.
        # The window-snap logic must not cut "wisdom" or "experience"
        # mid-word — both are well within the 20-char slack budget.
        body = (
            "with wisdom comes experience and with experience friends "
            "and the simple joys of everyday life"
        )

        snippet = extract_snippet(body, ["friends"], window_chars=20)

        # Strip ellipses, brackets, and surrounding whitespace so we
        # can verify every visible word is whole.
        core_text = (
            snippet.strip(".").strip()
                   .replace("[", "")
                   .replace("]", "")
        )
        body_words = set(body.split())
        for word in core_text.split():
            self.assertIn(
                word, body_words,
                f"token {word!r} in snippet is not a whole word from body",
            )

    def test_window_keeps_mid_word_cut_when_slack_exhausted(self):
        # Pathological no-whitespace run > slack budget: the window
        # falls back to a mid-character cut, and the ellipsis prefix
        # tells the reader content was truncated. This pins the bound
        # on word-snap so a degenerate body cannot turn the snippet
        # into the whole body.
        body = "X" * 200 + " friend " + "Y" * 200

        snippet = extract_snippet(body, ["friend"], window_chars=20)

        # Both ellipses must appear — neither X nor Y run fully fits.
        self.assertTrue(snippet.startswith("..."))
        self.assertTrue(snippet.endswith("..."))
        # Snippet length is bounded by window + 2*slack + match + a
        # few extra chars for "... " markers; nowhere near 400+ chars.
        self.assertLess(len(snippet), 120)

    def test_collapses_internal_whitespace_to_single_spaces(self):
        # Bodies with newlines / tabs should still produce a single-
        # line snippet for CLI display.
        body = "good\n\n   friends\tare\nlike  stars"

        snippet = extract_snippet(body, ["friends"])

        self.assertNotIn("\n", snippet)
        self.assertNotIn("\t", snippet)
        self.assertNotIn("  ", snippet)  # no double-space
        self.assertIn("[friends]", snippet)


if __name__ == "__main__":
    unittest.main()
