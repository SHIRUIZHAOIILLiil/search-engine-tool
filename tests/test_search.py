import unittest

from src.indexer import Index
from src.ranker import TFIDFRanker
from src.search import find_pages, find_phrase, print_word


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


if __name__ == "__main__":
    unittest.main()
