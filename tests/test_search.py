import unittest

from src.crawler import CrawledPage
from src.indexer import Index, build_index
from src.ranker import TFIDFRanker
from src.search import (
    find_pages,
    find_pages_with_snippets,
    find_phrase,
    find_phrase_with_snippets,
    format_did_you_mean,
    print_word,
    suggest_for_query,
)
from src.tokenizer import TokenizerConfig


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={
                "good": {
                    0: {"frequency": 1, "positions": [0]},
                    1: {"frequency": 1, "positions": [4]},
                },
                "friends": {
                    1: {"frequency": 1, "positions": [5]},
                },
            },
        )

    def test_print_word_returns_posting_case_insensitively(self):
        expected = {
            "page-1": {"frequency": 1, "positions": [0]},
            "page-2": {"frequency": 1, "positions": [4]},
        }

        self.assertEqual(print_word(self.index, "GOOD"), expected)

    def test_print_word_returns_empty_dict_for_missing_word(self):
        self.assertEqual(print_word(self.index, "missing"), {})

    def test_print_word_returns_empty_dict_for_punctuation_only_input(self):
        self.assertEqual(print_word(self.index, "!!!"), {})

    def test_print_word_uses_first_token_only(self):
        expected = {
            "page-1": {"frequency": 1, "positions": [0]},
            "page-2": {"frequency": 1, "positions": [4]},
        }

        self.assertEqual(print_word(self.index, "good friends"), expected)

    def test_find_pages_returns_pages_containing_all_words(self):
        self.assertEqual(find_pages(self.index, "good friends"), ["page-2"])

    def test_find_pages_returns_single_word_matches(self):
        self.assertEqual(find_pages(self.index, "good"), ["page-1", "page-2"])

    def test_find_pages_is_case_insensitive(self):
        self.assertEqual(find_pages(self.index, "GOOD FRIENDS"), ["page-2"])

    def test_find_pages_ignores_query_punctuation(self):
        self.assertEqual(find_pages(self.index, "good, friends!"), ["page-2"])

    def test_find_pages_handles_repeated_query_terms(self):
        self.assertEqual(find_pages(self.index, "good good"), ["page-1", "page-2"])

    def test_find_pages_handles_empty_and_missing_queries(self):
        self.assertEqual(find_pages(self.index, ""), [])
        self.assertEqual(find_pages(self.index, "missing"), [])

    def test_find_pages_returns_empty_list_when_one_query_term_is_missing(self):
        self.assertEqual(find_pages(self.index, "good missing"), [])

    def test_find_pages_uses_index_tokenizer_config_for_query(self):
        # Same idea as the phrase test below: build with stemming on,
        # then a user query in surface form must still match the stems
        # stored in the index. This pins the build/search consistency
        # invariant that motivates storing the config on the index.
        config = TokenizerConfig(apply_stemming=True)
        pages = [CrawledPage(url="page-1", text="cats are running")]
        index = build_index(pages, config=config)

        self.assertEqual(find_pages(index, "cats"), ["page-1"])
        self.assertEqual(find_pages(index, "running"), ["page-1"])

    def test_find_pages_ranks_documents_by_tf_idf_score(self):
        # Three docs; "alpha" and "beta" each appear in two of them so
        # idf > 0. Doc 1 has higher tf for "alpha" and should rank first
        # for the query "alpha beta".
        index = Index(
            documents={0: "low-tf", 1: "high-tf", 2: "no-match"},
            postings={
                "alpha": {
                    0: {"frequency": 1, "positions": [0]},
                    1: {"frequency": 5, "positions": [0, 1, 2, 3, 4]},
                },
                "beta": {
                    0: {"frequency": 1, "positions": [1]},
                    1: {"frequency": 1, "positions": [5]},
                },
            },
        )

        self.assertEqual(find_pages(index, "alpha beta"), ["high-tf", "low-tf"])

    def test_find_pages_default_ranker_is_tf_idf(self):
        # When idf is 0 (term in every document), TF-IDF returns 0 for
        # every candidate; ties resolve by doc_id ascending. Establishes
        # the default ranker's identity through observable behaviour.
        index = Index(
            documents={0: "page-A", 1: "page-B"},
            postings={
                "everywhere": {
                    0: {"frequency": 99, "positions": [0]},
                    1: {"frequency": 1, "positions": [0]},
                },
            },
        )

        # tf=99 doesn't beat tf=1 because both have idf=0; doc_id wins.
        self.assertEqual(find_pages(index, "everywhere"), ["page-A", "page-B"])

    def test_find_pages_accepts_custom_ranker_for_dependency_injection(self):
        # Stub ranker that prefers higher doc_id, the inverse of the
        # TFIDFRanker tiebreak. Demonstrates the ranker parameter is
        # honoured rather than ignored in favour of the default.
        class FavorHigherDocIdRanker:
            def score(self, index, query_tokens, doc_id):
                return float(doc_id)

        index = Index(
            documents={0: "page-A", 1: "page-B", 2: "page-C"},
            postings={
                "term": {
                    0: {"frequency": 1, "positions": [0]},
                    1: {"frequency": 1, "positions": [0]},
                    2: {"frequency": 1, "positions": [0]},
                },
            },
        )

        # Default TFIDF would tie everything → ascending doc_id order.
        # The custom ranker reverses that.
        self.assertEqual(
            find_pages(index, "term", ranker=FavorHigherDocIdRanker()),
            ["page-C", "page-B", "page-A"],
        )

        # And re-confirm the default order without the override:
        self.assertEqual(
            find_pages(index, "term", ranker=TFIDFRanker()),
            ["page-A", "page-B", "page-C"],
        )


class FindPhraseTests(unittest.TestCase):
    def test_returns_pages_containing_consecutive_phrase(self):
        # Doc A has "good" at 3, "friends" at 4 → adjacent → match.
        # Doc B has "good" at 10, "friends" at 20 → not adjacent → miss.
        index = Index(
            documents={0: "page-A", 1: "page-B"},
            postings={
                "good": {
                    0: {"frequency": 1, "positions": [3]},
                    1: {"frequency": 1, "positions": [10]},
                },
                "friends": {
                    0: {"frequency": 1, "positions": [4]},
                    1: {"frequency": 1, "positions": [20]},
                },
            },
            doc_lengths={0: 10, 1: 30},
        )

        self.assertEqual(find_phrase(index, "good friends"), ["page-A"])

    def test_returns_empty_when_phrase_is_never_consecutive(self):
        index = Index(
            documents={0: "page-1"},
            postings={
                "good": {0: {"frequency": 1, "positions": [3]}},
                "friends": {0: {"frequency": 1, "positions": [10]}},
            },
            doc_lengths={0: 50},
        )

        self.assertEqual(find_phrase(index, "good friends"), [])

    def test_returns_empty_for_empty_query(self):
        index = Index(
            documents={0: "page-1"},
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
            doc_lengths={0: 10},
        )

        self.assertEqual(find_phrase(index, ""), [])

    def test_find_phrase_uses_index_tokenizer_config_for_query(self):
        # Build an index with stemming enabled, so "running" → "run".
        # The user types the un-stemmed surface form; find_phrase must
        # apply the same config when tokenising the query so the query
        # tokens line up with the index keys.
        config = TokenizerConfig(apply_stemming=True)
        pages = [CrawledPage(url="page-1", text="i love running marathons")]
        index = build_index(pages, config=config)

        # Without applying the index's config to the query, "running"
        # wouldn't match the indexed stem "run" and we'd get [].
        self.assertEqual(find_phrase(index, "running marathon"), ["page-1"])

    def test_default_ranker_orders_tied_phrase_matches_by_doc_id(self):
        # Both docs contain the phrase "alpha beta" and both terms occur
        # in every document → idf=0 → scores tie → fall back to doc_id.
        index = Index(
            documents={0: "page-A", 1: "page-B"},
            postings={
                "alpha": {
                    0: {"frequency": 1, "positions": [3]},
                    1: {"frequency": 1, "positions": [7]},
                },
                "beta": {
                    0: {"frequency": 1, "positions": [4]},
                    1: {"frequency": 1, "positions": [8]},
                },
            },
            doc_lengths={0: 10, 1: 20},
        )

        self.assertEqual(find_phrase(index, "alpha beta"), ["page-A", "page-B"])


class FindPagesWithSnippetsTests(unittest.TestCase):
    """v1.4.0: ``find_pages`` now has a sibling that pairs each URL
    with a context excerpt from the body. Preserves the original
    ranking/match contract so existing `find_pages` tests still hold;
    these new tests pin the snippet half of the pair.
    """

    def setUp(self):
        self.index = Index(
            documents={
                0: "page-1",
                1: "page-2",
            },
            documents_text={
                0: "Good friends are like stars; you don't always see them.",
                1: "Good morning, sunshine; the day is fresh and new.",
            },
            postings={
                "good": {
                    0: {"frequency": 1, "positions": [0]},
                    1: {"frequency": 1, "positions": [0]},
                },
                "friends": {
                    0: {"frequency": 1, "positions": [1]},
                },
            },
        )

    def test_returns_url_plus_snippet_pairs_for_each_match(self):
        results = find_pages_with_snippets(self.index, "good friends")

        self.assertEqual(len(results), 1)
        url, snippet = results[0]
        self.assertEqual(url, "page-1")
        self.assertIn("[Good]", snippet)
        self.assertIn("[friends]", snippet)

    def test_url_order_matches_find_pages(self):
        # Same retrieval contract -> same ordering. Locks the
        # invariant that switching the CLI to the snippet variant
        # cannot reshuffle the ranking under the user's feet.
        plain = find_pages(self.index, "good")
        snippet_urls = [url for url, _ in find_pages_with_snippets(self.index, "good")]

        self.assertEqual(snippet_urls, plain)

    def test_returns_empty_snippet_when_document_has_no_body_text(self):
        # A v4 legacy index has documents_text empty by default; the
        # find variant must still surface the URL — only the snippet
        # half degrades. Pins backward compatibility.
        legacy_index = Index(
            documents={0: "page-legacy"},
            documents_text={},  # explicitly empty -- pre-v1.4.0 shape
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
        )

        results = find_pages_with_snippets(legacy_index, "good")

        self.assertEqual(results, [("page-legacy", "")])

    def test_empty_query_returns_empty_list(self):
        self.assertEqual(find_pages_with_snippets(self.index, ""), [])

    def test_no_matches_returns_empty_list(self):
        self.assertEqual(find_pages_with_snippets(self.index, "nonexistent"), [])


class FindPhraseWithSnippetsTests(unittest.TestCase):
    def test_phrase_snippet_highlights_whole_phrase_as_one_unit(self):
        index = Index(
            documents={0: "page-1"},
            documents_text={
                0: "We are all good friends here, sharing the day.",
            },
            postings={
                "good": {0: {"frequency": 1, "positions": [3]}},
                "friends": {0: {"frequency": 1, "positions": [4]}},
            },
            doc_lengths={0: 10},
        )

        results = find_phrase_with_snippets(index, "good friends")

        self.assertEqual(len(results), 1)
        _, snippet = results[0]
        # Phrase mode brackets the contiguous match, not each token.
        self.assertIn("[good friends]", snippet)
        self.assertNotIn("[good] [friends]", snippet)

    def test_phrase_with_no_consecutive_match_returns_empty_list(self):
        index = Index(
            documents={0: "page-1"},
            documents_text={
                0: "Good ideas come from many friends, but not together.",
            },
            postings={
                "good": {0: {"frequency": 1, "positions": [0]}},
                "friends": {0: {"frequency": 1, "positions": [5]}},
            },
            doc_lengths={0: 10},
        )

        # The phrase filter rejects this; no result regardless of snippet.
        self.assertEqual(find_phrase_with_snippets(index, "good friends"), [])

    def test_phrase_snippet_with_empty_body_returns_url_and_empty_snippet(self):
        index = Index(
            documents={0: "page-1"},
            documents_text={},
            postings={
                "good": {0: {"frequency": 1, "positions": [0]}},
                "friends": {0: {"frequency": 1, "positions": [1]}},
            },
            doc_lengths={0: 2},
        )

        results = find_phrase_with_snippets(index, "good friends")

        self.assertEqual(results, [("page-1", "")])


class SuggestForQueryTests(unittest.TestCase):
    def setUp(self):
        # A tiny vocabulary that gives us deliberate near-misses for
        # canonical typos: indi*erence / friend* / good*.
        self.index = Index(
            documents={0: "page-1"},
            postings={
                "indifference": {0: {"frequency": 1, "positions": [0]}},
                "indignant": {0: {"frequency": 1, "positions": [1]}},
                "friend": {0: {"frequency": 1, "positions": [2]}},
                "friendly": {0: {"frequency": 1, "positions": [3]}},
                "good": {0: {"frequency": 1, "positions": [4]}},
                "goodness": {0: {"frequency": 1, "positions": [5]}},
            },
        )

    def test_returns_empty_when_every_token_in_vocabulary(self):
        # Known query is not a typo candidate — keeps "did you mean"
        # noise out of legitimate find calls that simply return zero
        # pages because of the AND filter.
        self.assertEqual(suggest_for_query(self.index, "good friend"), {})

    def test_returns_candidates_for_unknown_token(self):
        result = suggest_for_query(self.index, "indiference")
        self.assertIn("indiference", result)
        self.assertIn("indifference", result["indiference"])

    def test_applies_index_tokenizer_config_for_case_insensitivity(self):
        # Tokeniser lowercases by default; suggestion should follow
        # the same path so a typo with uppercase chars still resolves.
        result = suggest_for_query(self.index, "Indiference")
        self.assertIn("indiference", result)
        self.assertIn("indifference", result["indiference"])

    def test_empty_query_returns_empty_mapping(self):
        self.assertEqual(suggest_for_query(self.index, ""), {})

    def test_no_candidate_within_threshold_returns_empty_list(self):
        # "xyzqq" has nothing within edit distance 2 of any vocab term.
        result = suggest_for_query(self.index, "xyzqq")
        self.assertEqual(result, {"xyzqq": []})


class FormatDidYouMeanTests(unittest.TestCase):
    def setUp(self):
        self.index = Index(
            documents={0: "page-1"},
            postings={
                "indifference": {0: {"frequency": 1, "positions": [0]}},
                "friend": {0: {"frequency": 1, "positions": [1]}},
                "good": {0: {"frequency": 1, "positions": [2]}},
            },
        )

    def test_returns_none_when_every_token_in_vocab(self):
        # Zero results when query is valid is an AND-filter miss, not
        # a typo — a "did you mean" hint would mislead the user.
        self.assertIsNone(format_did_you_mean(self.index, "good friend"))

    def test_returns_none_for_empty_query(self):
        self.assertIsNone(format_did_you_mean(self.index, ""))

    def test_returns_reformulated_single_token_query(self):
        hint = format_did_you_mean(self.index, "indiference")
        self.assertEqual(hint, "Did you mean: indifference?")

    def test_returns_reformulated_multi_token_query_preserving_order(self):
        # Order matters — the reformulation must read in the original
        # word order so the user can copy-paste it back into find.
        hint = format_did_you_mean(self.index, "indiference godo")
        self.assertEqual(hint, "Did you mean: indifference good?")

    def test_keeps_known_tokens_verbatim_in_reformulation(self):
        hint = format_did_you_mean(self.index, "good indiference")
        # "good" is in vocab, passes through; "indiference" is corrected.
        self.assertEqual(hint, "Did you mean: good indifference?")

    def test_returns_none_when_no_unknown_token_has_a_candidate(self):
        # "xyzqq" is unknown but has nothing within edit distance 2
        # — nothing useful to suggest, stay silent.
        self.assertIsNone(format_did_you_mean(self.index, "xyzqq"))

    def test_keeps_uncorrectable_token_alongside_correctable_one(self):
        # If at least one token has a candidate, surface the line —
        # uncorrectable tokens pass through so the user still sees
        # every word they typed in the reformulation.
        hint = format_did_you_mean(self.index, "indiference xyzqq")
        self.assertEqual(hint, "Did you mean: indifference xyzqq?")


if __name__ == "__main__":
    unittest.main()
