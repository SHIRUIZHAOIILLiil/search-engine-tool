import json
import unittest

from tempfile import TemporaryDirectory

from src.crawler import CrawledPage
from src.indexer import INDEX_VERSION, Index, build_index, load_index, save_index, tokenize


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

        self.assertEqual(index.data["good"]["page-1"]["frequency"], 2)
        self.assertEqual(index.data["good"]["page-1"]["positions"], [0, 3])
        self.assertEqual(index.data["friends"]["page-1"]["positions"], [1])

    def test_build_index_keeps_pages_separate(self):
        pages = [
            CrawledPage(url="page-1", text="good good"),
            CrawledPage(url="page-2", text="good"),
        ]

        index = build_index(pages)

        self.assertEqual(index.data["good"]["page-1"]["frequency"], 2)
        self.assertEqual(index.data["good"]["page-1"]["positions"], [0, 1])
        self.assertEqual(index.data["good"]["page-2"]["frequency"], 1)
        self.assertEqual(index.data["good"]["page-2"]["positions"], [0])

    def test_build_index_handles_empty_page_text(self):
        pages = [CrawledPage(url="page-1", text="")]

        index = build_index(pages)

        self.assertEqual(index, Index())

    def test_build_index_stamps_current_schema_version(self):
        index = build_index([])

        self.assertEqual(index.version, INDEX_VERSION)

    def test_save_and_load_index_round_trip(self):
        index = Index(
            data={
                "good": {
                    "page-1": {"frequency": 2, "positions": [0, 3]},
                },
            },
        )

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"

            save_index(index, path)
            loaded_index = load_index(path)

        self.assertEqual(loaded_index, index)

    def test_save_index_writes_schema_version_to_disk(self):
        index = Index(data={"good": {"page-1": {"frequency": 1, "positions": [0]}}})

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"

            save_index(index, path)
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)

        self.assertEqual(payload["version"], INDEX_VERSION)

    def test_load_index_rejects_file_with_wrong_version(self):
        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"version": INDEX_VERSION + 999, "data": {}}, fh)

            with self.assertRaises(ValueError):
                load_index(path)

    def test_load_index_rejects_file_without_version_field(self):
        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"good": {"page-1": {"frequency": 1, "positions": [0]}}}, fh)

            with self.assertRaises(ValueError):
                load_index(path)

    def test_load_index_raises_error_for_missing_file(self):
        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/missing.json"

            with self.assertRaises(FileNotFoundError):
                load_index(path)


if __name__ == "__main__":
    unittest.main()
