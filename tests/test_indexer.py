import unittest

from src.crawler import CrawledPage
from src.indexer import build_index, tokenize


class IndexerTests(unittest.TestCase):
    def test_tokenize_is_case_insensitive(self):
        self.assertEqual(tokenize("Good, GOOD friend's"), ["good", "good", "friend's"])

    def test_tokenize_handles_empty_text(self):
        self.assertEqual(tokenize(""), [])

    def test_tokenize_ignores_punctuation(self):
        self.assertEqual(tokenize("Hello... world!"), ["hello", "world"])

    def test_tokenize_keeps_numbers(self):
        self.assertEqual(tokenize("Page 10 has 2 quotes"), ["page", "10", "has", "2", "quotes"])

    def test_build_index_records_frequency_and_positions(self):
        pages = [CrawledPage(url="page-1", text="Good friends are good")]

        index = build_index(pages)

        self.assertEqual(index["good"]["page-1"]["frequency"], 2)
        self.assertEqual(index["good"]["page-1"]["positions"], [0, 3])
        self.assertEqual(index["friends"]["page-1"]["positions"], [1])

    def test_build_index_keeps_pages_separate(self):
        pages = [
            CrawledPage(url="page-1", text="good good"),
            CrawledPage(url="page-2", text="good"),
        ]

        index = build_index(pages)

        self.assertEqual(index["good"]["page-1"]["frequency"], 2)
        self.assertEqual(index["good"]["page-1"]["positions"], [0, 1])
        self.assertEqual(index["good"]["page-2"]["frequency"], 1)
        self.assertEqual(index["good"]["page-2"]["positions"], [0])

    def test_build_index_handles_empty_page_text(self):
        pages = [CrawledPage(url="page-1", text="")]

        index = build_index(pages)

        self.assertEqual(index, {})

if __name__ == "__main__":
    unittest.main()
