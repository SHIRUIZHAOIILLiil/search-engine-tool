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

    def test_find_pages_returns_pages_containing_all_words(self):
        self.assertEqual(find_pages(self.index, "good friends"), ["page-2"])

    def test_find_pages_handles_empty_and_missing_queries(self):
        self.assertEqual(find_pages(self.index, ""), [])
        self.assertEqual(find_pages(self.index, "missing"), [])


if __name__ == "__main__":
    unittest.main()
