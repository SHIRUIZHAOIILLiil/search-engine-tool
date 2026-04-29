import unittest

from src.crawler import CrawledPage
from src.indexer import build_index, tokenize


class IndexerTests(unittest.TestCase):
    def test_tokenize_is_case_insensitive(self):
        self.assertEqual(tokenize("Good, GOOD friend's"), ["good", "good", "friend's"])

    def test_build_index_records_frequency_and_positions(self):
        pages = [CrawledPage(url="page-1", text="Good friends are good")]

        index = build_index(pages)

        self.assertEqual(index["good"]["page-1"]["frequency"], 2)
        self.assertEqual(index["good"]["page-1"]["positions"], [0, 3])
        self.assertEqual(index["friends"]["page-1"]["positions"], [1])


if __name__ == "__main__":
    unittest.main()
