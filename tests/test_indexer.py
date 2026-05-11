import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.crawler import CrawledPage
from src.indexer import INDEX_VERSION, Index, build_index, load_index, save_index
from src.parser import ParsedFields
from src.tokenizer import TokenizerConfig, tokenize


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

    def test_build_index_persists_body_text_for_each_document(self):
        # New in v1.4.0 (INDEX_VERSION 5): the snippet generator needs
        # the raw body text per doc, so build_index now mirrors
        # ``CrawledPage.text`` into ``Index.documents_text`` keyed by
        # the same int doc_id used in ``documents`` and ``postings``.
        pages = [
            CrawledPage(url="page-1", text="good friends are stars"),
            CrawledPage(url="page-2", text="good morning sunshine"),
        ]

        index = build_index(pages)

        self.assertEqual(index.documents_text[0], "good friends are stars")
        self.assertEqual(index.documents_text[1], "good morning sunshine")
        # Same key space as ``documents`` — invariant the snippet
        # generator relies on (doc_id from postings -> URL -> text
        # all roundtrip through the same int).
        self.assertEqual(set(index.documents_text.keys()), set(index.documents.keys()))

    def test_build_index_overwrites_body_text_when_same_url_seen_twice(self):
        # Duplicate URL collapses to one doc_id (per the existing
        # contract); the later body text wins so the snippet reflects
        # the most recent crawl content.
        pages = [
            CrawledPage(url="page-1", text="first crawl content"),
            CrawledPage(url="page-1", text="updated crawl content"),
        ]

        index = build_index(pages)

        self.assertEqual(len(index.documents_text), 1)
        self.assertEqual(index.documents_text[0], "updated crawl content")

    def test_save_and_load_round_trip_preserves_documents_text(self):
        # The body text must survive the JSON roundtrip — otherwise
        # ``load`` followed by snippet generation would silently
        # produce empty snippets without anyone noticing.
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            documents_text={
                0: "good friends are stars",
                1: "good morning sunshine",
            },
            postings={
                "good": {
                    0: {"frequency": 1, "positions": [0]},
                    1: {"frequency": 1, "positions": [0]},
                },
            },
        )

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"
            save_index(index, path)
            loaded = load_index(path)

        self.assertEqual(loaded.documents_text, index.documents_text)

    def test_save_index_serialises_documents_text_with_stringified_doc_ids(self):
        # JSON requires string keys; document_text in particular must
        # stay parallel to ``documents`` in stringification so a future
        # external consumer (e.g. a debugging script) can join the two.
        index = Index(
            documents={0: "page-1"},
            documents_text={0: "alpha beta"},
            postings={"alpha": {0: {"frequency": 1, "positions": [0]}}},
        )

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"
            save_index(index, path)
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)

        self.assertIn("documents_text", payload)
        self.assertEqual(payload["documents_text"], {"0": "alpha beta"})

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

    def test_build_index_stores_tokenizer_config_on_index(self):
        config = TokenizerConfig(apply_stemming=True)

        index = build_index([], config=config)

        self.assertEqual(index.tokenizer_config, config)

    def test_build_index_applies_tokenizer_config_to_body_tokens(self):
        # Stemming maps "running" → "run", "cats" → "cat" — verify the
        # index keys reflect the stem, not the surface form.
        config = TokenizerConfig(apply_stemming=True)
        pages = [CrawledPage(url="page-1", text="running cats")]

        index = build_index(pages, config=config)

        self.assertIn("run", index.postings)
        self.assertIn("cat", index.postings)
        self.assertNotIn("running", index.postings)
        self.assertNotIn("cats", index.postings)

    def test_build_index_default_config_preserves_brief_behaviour(self):
        # No config supplied → no stemming or stopword filtering, so
        # the index keys are the raw lowercased tokens (the brief's
        # default contract).
        pages = [CrawledPage(url="page-1", text="running cats")]

        index = build_index(pages)

        self.assertIn("running", index.postings)
        self.assertIn("cats", index.postings)
        self.assertEqual(index.tokenizer_config, TokenizerConfig())

    def test_save_and_load_preserves_tokenizer_config(self):
        config = TokenizerConfig(apply_stemming=True, apply_stopword_filter=True)
        index = Index(
            documents={0: "page-1"},
            postings={"foo": {0: {"frequency": 1, "positions": [0], "fields": {}}}},
            doc_lengths={0: 1},
            tokenizer_config=config,
        )

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"

            save_index(index, path)
            loaded_index = load_index(path)

        self.assertEqual(loaded_index.tokenizer_config, config)

    def test_load_index_raises_error_for_missing_file(self):
        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/missing.json"

            with self.assertRaises(FileNotFoundError):
                load_index(path)


class SaveIndexAtomicityTests(unittest.TestCase):
    """``save_index`` must not corrupt the destination on partial failure.

    The threat model: a developer runs ``build``, Ctrl+C lands halfway
    through serialisation, and the next ``load`` reads a half-written
    file. The fix is to write a sibling ``.tmp`` file and only swap
    it into place via :func:`os.replace` (atomic on POSIX + Windows).
    These tests pin both halves of the contract — happy path still
    works, failure path leaves the previous good file intact.
    """

    def _two_distinct_indexes(self):
        # Two indexes whose serialised JSON differs in every key so a
        # partial overwrite would be obvious if it occurred.
        old_pages = [CrawledPage(url="page-old", text="alpha beta")]
        new_pages = [CrawledPage(url="page-new", text="gamma delta epsilon")]
        return build_index(old_pages), build_index(new_pages)

    def test_save_writes_via_temp_file_and_replaces_atomically(self):
        # Happy path: the temporary sibling appears during the write
        # and is gone after os.replace. We assert both via a patched
        # os.replace that observes the filesystem state right before
        # the rename is committed.
        index = build_index([CrawledPage(url="page-1", text="alpha beta")])
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "index.json"
            tmp_seen: dict[str, bool] = {"tmp_existed_pre_replace": False}

            real_replace = __import__("os").replace

            def observing_replace(src, dst):
                tmp_seen["tmp_existed_pre_replace"] = Path(src).exists()
                return real_replace(src, dst)

            with patch("src.indexer.os.replace", side_effect=observing_replace):
                save_index(index, path)

            self.assertTrue(
                tmp_seen["tmp_existed_pre_replace"],
                "save_index must stage content via a .tmp sibling before replace",
            )
            self.assertTrue(path.exists(), "destination must exist after save")
            self.assertFalse(
                path.with_name(path.name + ".tmp").exists(),
                "successful save must clean up the .tmp sibling via replace",
            )

    def test_crash_during_replace_leaves_previous_file_intact(self):
        # Failure path: a previously saved index sits at the path; a
        # second save then crashes inside os.replace. The destination
        # must still be the original content, byte-for-byte.
        original_index, new_index = self._two_distinct_indexes()
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "index.json"
            save_index(original_index, path)
            original_bytes = path.read_bytes()

            with patch(
                "src.indexer.os.replace",
                side_effect=OSError("simulated crash during atomic rename"),
            ):
                with self.assertRaises(OSError):
                    save_index(new_index, path)

            self.assertEqual(
                path.read_bytes(),
                original_bytes,
                "atomic write contract: a failed save must not change the on-disk file",
            )

    def test_crash_during_tmp_write_leaves_previous_file_intact(self):
        # Failure earlier in the pipeline — Path.write_text raises
        # halfway through, e.g. ENOSPC. Same invariant: the original
        # file is unchanged.
        original_index, new_index = self._two_distinct_indexes()
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "index.json"
            save_index(original_index, path)
            original_bytes = path.read_bytes()

            with patch.object(
                Path,
                "write_text",
                side_effect=OSError("simulated ENOSPC during temp write"),
            ):
                with self.assertRaises(OSError):
                    save_index(new_index, path)

            self.assertEqual(
                path.read_bytes(),
                original_bytes,
                "a temp-write failure must not touch the original file",
            )


if __name__ == "__main__":
    unittest.main()
