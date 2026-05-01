import unittest

from src.search import find_pages, print_word


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.index = {
            "good": {
                "page-1": {"frequency": 1, "positions": [0]},
                "page-2": {"frequency": 1, "positions": [4]},
            },
            "friends": {
                "page-2": {"frequency": 1, "positions": [5]},
            },
        }

    def test_print_word_returns_posting_case_insensitively(self):
        self.assertEqual(print_word(self.index, "GOOD"), self.index["good"])

    def test_print_word_returns_empty_dict_for_missing_word(self):
        self.assertEqual(print_word(self.index, "missing"), {})

    def test_print_word_returns_empty_dict_for_punctuation_only_input(self):
        self.assertEqual(print_word(self.index, "!!!"), {})

    def test_print_word_uses_first_token_only(self):
        self.assertEqual(print_word(self.index, "good friends"), self.index["good"])

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


if __name__ == "__main__":
    unittest.main()
