import json
import unittest

from tempfile import TemporaryDirectory

from src.crawler import CrawledPage
from src.indexer import INDEX_VERSION, Index, build_index, load_index, save_index, tokenize
from src.parser import ParsedFields


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

        self.assertEqual(index.documents, {0: "page-1"})
        self.assertEqual(index.postings["good"][0]["frequency"], 2)
        self.assertEqual(index.postings["good"][0]["positions"], [0, 3])
        self.assertEqual(index.postings["friends"][0]["positions"], [1])

    def test_build_index_keeps_pages_separate(self):
        pages = [
            CrawledPage(url="page-1", text="good good"),
            CrawledPage(url="page-2", text="good"),
        ]

        index = build_index(pages)

        self.assertEqual(index.documents, {0: "page-1", 1: "page-2"})
        self.assertEqual(index.postings["good"][0]["frequency"], 2)
        self.assertEqual(index.postings["good"][0]["positions"], [0, 1])
        self.assertEqual(index.postings["good"][1]["frequency"], 1)
        self.assertEqual(index.postings["good"][1]["positions"], [0])

    def test_build_index_assigns_sequential_doc_ids(self):
        pages = [
            CrawledPage(url="page-a", text="alpha"),
            CrawledPage(url="page-b", text="beta"),
            CrawledPage(url="page-c", text="gamma"),
        ]

        index = build_index(pages)

        self.assertEqual(
            index.documents,
            {0: "page-a", 1: "page-b", 2: "page-c"},
        )

    def test_build_index_reuses_doc_id_for_repeated_url(self):
        pages = [
            CrawledPage(url="page-1", text="alpha beta"),
            CrawledPage(url="page-1", text="gamma"),
        ]

        index = build_index(pages)

        self.assertEqual(index.documents, {0: "page-1"})
        self.assertEqual(index.postings["alpha"][0]["frequency"], 1)
        self.assertEqual(index.postings["gamma"][0]["frequency"], 1)

    def test_build_index_handles_empty_page_text(self):
        pages = [CrawledPage(url="page-1", text="")]

        index = build_index(pages)

        self.assertEqual(index.documents, {0: "page-1"})
        self.assertEqual(index.postings, {})

    def test_build_index_stamps_current_schema_version(self):
        index = build_index([])

        self.assertEqual(index.version, INDEX_VERSION)

    def test_build_index_records_per_field_breakdown(self):
        fields = ParsedFields(
            title="Quotes to Scrape",
            quote_texts=["good is the way"],
            authors=["Good Friend"],
            tags=["good"],
            body="Quotes to Scrape good is the way Good Friend good",
        )
        pages = [CrawledPage(url="page-1", text=fields.body, fields=fields)]

        index = build_index(pages)

        posting = index.postings["good"][0]
        # body sees three "good" occurrences (once each from quote / author / tag).
        self.assertEqual(posting["frequency"], 3)
        # Per-field breakdown isolates each occurrence to its slot. The
        # storage is sparse: fields with frequency 0 are simply absent
        # (consumers must treat a missing key as frequency=0).
        self.assertNotIn("title", posting["fields"])
        self.assertEqual(posting["fields"]["quote_text"]["frequency"], 1)
        self.assertEqual(posting["fields"]["author"]["frequency"], 1)
        self.assertEqual(posting["fields"]["tag"]["frequency"], 1)

    def test_build_index_indexes_title_only_tokens(self):
        fields = ParsedFields(
            title="UniqueTitleWord",
            body="completely different body text",
        )
        pages = [CrawledPage(url="page-1", text=fields.body, fields=fields)]

        index = build_index(pages)

        self.assertIn("uniquetitleword", index.postings)
        posting = index.postings["uniquetitleword"][0]
        # The token never appears in the body, so the body-level stats stay
        # empty — but the per-field breakdown records it under "title" so
        # a future field-aware ranker can still surface this page.
        self.assertEqual(posting["frequency"], 0)
        self.assertEqual(posting["positions"], [])
        self.assertEqual(posting["fields"]["title"]["frequency"], 1)

    def test_build_index_creates_empty_fields_dict_for_unstructured_pages(self):
        # CrawledPage without an explicit ParsedFields uses the default,
        # all-empty fields. The posting must still expose a fields slot
        # so consumers can rely on its presence.
        page = CrawledPage(url="page-1", text="hello world")

        index = build_index([page])

        self.assertEqual(index.postings["hello"][0]["fields"], {})

    def test_build_index_records_doc_lengths_in_body_tokens(self):
        pages = [
            CrawledPage(url="page-1", text="alpha beta gamma"),
            CrawledPage(url="page-2", text="delta"),
        ]

        index = build_index(pages)

        # Body lengths are token counts, not character counts.
        self.assertEqual(index.doc_lengths, {0: 3, 1: 1})

    def test_build_index_records_zero_length_for_empty_body(self):
        pages = [CrawledPage(url="page-1", text="")]

        index = build_index(pages)

        self.assertEqual(index.doc_lengths, {0: 0})

    def test_build_index_doc_length_accumulates_for_repeated_url(self):
        # Repeated URL re-uses the same doc_id, so postings accumulate;
        # the body length must accumulate the same way so BM25 sees the
        # full token count later.
        pages = [
            CrawledPage(url="page-1", text="alpha beta"),
            CrawledPage(url="page-1", text="gamma"),
        ]

        index = build_index(pages)

        self.assertEqual(index.doc_lengths, {0: 3})

    def test_save_and_load_index_round_trip_preserves_doc_lengths(self):
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={
                "good": {
                    0: {"frequency": 1, "positions": [0], "fields": {}},
                    1: {"frequency": 1, "positions": [4], "fields": {}},
                },
            },
            doc_lengths={0: 5, 1: 12},
        )

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"

            save_index(index, path)
            loaded_index = load_index(path)

        self.assertEqual(loaded_index.doc_lengths, {0: 5, 1: 12})
        self.assertEqual(loaded_index, index)

    def test_save_and_load_index_round_trip_preserves_fields(self):
        fields = ParsedFields(
            title="Title text",
            quote_texts=["good quote"],
            body="Title text good quote",
        )
        pages = [CrawledPage(url="page-1", text=fields.body, fields=fields)]
        index = build_index(pages)

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"

            save_index(index, path)
            loaded_index = load_index(path)

        self.assertEqual(loaded_index, index)
        self.assertEqual(
            loaded_index.postings["good"][0]["fields"]["quote_text"]["frequency"],
            1,
        )

    def test_save_and_load_index_round_trip(self):
        index = Index(
            documents={0: "page-1"},
            postings={
                "good": {0: {"frequency": 2, "positions": [0, 3]}},
            },
        )

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"

            save_index(index, path)
            loaded_index = load_index(path)

        self.assertEqual(loaded_index, index)

    def test_save_index_writes_schema_version_to_disk(self):
        index = Index(
            documents={0: "page-1"},
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
        )

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"

            save_index(index, path)
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)

        self.assertEqual(payload["version"], INDEX_VERSION)

    def test_save_index_serialises_doc_ids_as_strings(self):
        index = Index(
            documents={0: "page-1"},
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
        )

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"

            save_index(index, path)
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)

        # JSON requires string keys; loader converts them back to int.
        self.assertIn("0", payload["documents"])
        self.assertIn("0", payload["postings"]["good"])

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
