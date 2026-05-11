import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from src.crawler import CrawledPage
from src.indexer import Index
from src.main import _ensure_utf8_output, handle_command


class MainCommandTests(unittest.TestCase):
    def test_help_command_prints_available_commands(self):
        output = io.StringIO()

        with redirect_stdout(output):
            returned_index = handle_command("help", Index())

        self.assertEqual(returned_index, Index())
        self.assertIn("build", output.getvalue())
        self.assertIn("find <query>", output.getvalue())

    def test_unknown_command_raises_value_error(self):
        with self.assertRaises(ValueError):
            handle_command("unknown", Index())

    def test_exit_command_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            handle_command("exit", Index())

    def test_quit_command_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            handle_command("quit", Index())

    def test_print_command_requires_word_argument(self):
        with self.assertRaises(ValueError):
            handle_command("print", Index())

    def test_find_command_requires_query_argument(self):
        with self.assertRaises(ValueError):
            handle_command("find", Index())

    def test_print_command_outputs_posting_list(self):
        index = Index(
            documents={0: "page-1"},
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
        )
        output = io.StringIO()

        with redirect_stdout(output):
            returned_index = handle_command("print good", index)

        self.assertIs(returned_index, index)
        self.assertIn('"frequency": 1', output.getvalue())
        self.assertIn('"page-1"', output.getvalue())

    def test_find_command_outputs_matching_pages(self):
        index = Index(
            documents={0: "page-1"},
            postings={
                "good": {0: {"frequency": 1, "positions": [0]}},
                "friends": {0: {"frequency": 1, "positions": [1]}},
            },
        )
        output = io.StringIO()

        with redirect_stdout(output):
            returned_index = handle_command("find good friends", index)

        self.assertIs(returned_index, index)
        self.assertIn("page-1", output.getvalue())

    def test_find_command_prints_indented_snippet_below_url(self):
        # v1.4.0: each result line is followed by an indented context
        # snippet that highlights the query tokens. Verifies the
        # two-line format and the bracket markup carry through.
        index = Index(
            documents={0: "https://example.com/page-1"},
            documents_text={
                0: "Good friends are like stars in the night sky.",
            },
            postings={
                "good": {0: {"frequency": 1, "positions": [0]}},
                "friends": {0: {"frequency": 1, "positions": [1]}},
            },
        )
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command("find good friends", index)

        text = output.getvalue()
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "https://example.com/page-1")
        # Indented snippet line follows.
        self.assertTrue(lines[1].startswith("  "),
                        f"Expected snippet line to be indented; got {lines[1]!r}")
        self.assertIn("[Good]", lines[1])
        self.assertIn("[friends]", lines[1])

    def test_find_command_falls_back_to_url_only_when_snippet_is_empty(self):
        # Legacy index (no documents_text) -> empty snippet -> output
        # collapses to the URL alone with no dangling blank-indent line.
        index = Index(
            documents={0: "https://example.com/page-1"},
            documents_text={},  # legacy / empty
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
        )
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command("find good", index)

        lines = output.getvalue().strip().splitlines()
        self.assertEqual(lines, ["https://example.com/page-1"])

    def test_find_command_phrase_mode_uses_phrase_highlighting(self):
        # Quoted query routes to phrase mode; the snippet must bracket
        # the whole phrase as one unit, not each token independently.
        index = Index(
            documents={0: "https://example.com/page-1"},
            documents_text={
                0: "We are all good friends here, sharing the journey.",
            },
            postings={
                "good": {0: {"frequency": 1, "positions": [3]}},
                "friends": {0: {"frequency": 1, "positions": [4]}},
            },
            doc_lengths={0: 10},
        )
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command('find "good friends"', index)

        text = output.getvalue()
        self.assertIn("[good friends]", text)
        self.assertNotIn("[good] [friends]", text)

    def test_find_command_routes_quoted_argument_to_phrase_mode(self):
        # v1.4.0: main.py imports the ``_with_snippets`` variants so it
        # can print URL + context excerpt per result; patches follow.
        output = io.StringIO()

        with patch(
            "src.main.find_phrase_with_snippets",
            return_value=[("page-1", "")],
        ) as find_phrase_mock:
            with patch("src.main.find_pages_with_snippets") as find_pages_mock:
                with redirect_stdout(output):
                    handle_command('find "good friends"', Index())

        # The phrase function is called once with the quoted text
        # (no extra splitting) and the conjunctive path is skipped.
        find_phrase_mock.assert_called_once()
        self.assertEqual(find_phrase_mock.call_args.args[1], "good friends")
        find_pages_mock.assert_not_called()
        self.assertIn("page-1", output.getvalue())

    def test_find_command_routes_unquoted_args_to_conjunctive_mode(self):
        output = io.StringIO()

        with patch("src.main.find_phrase_with_snippets") as find_phrase_mock:
            with patch(
                "src.main.find_pages_with_snippets",
                return_value=[("page-1", "")],
            ) as find_pages_mock:
                with redirect_stdout(output):
                    handle_command("find good friends", Index())

        # Unquoted input is the brief's documented AND form.
        find_pages_mock.assert_called_once()
        self.assertEqual(find_pages_mock.call_args.args[1], "good friends")
        find_phrase_mock.assert_not_called()

    def test_find_command_reports_no_matches(self):
        output = io.StringIO()

        with redirect_stdout(output):
            returned_index = handle_command("find missing", Index())

        self.assertEqual(returned_index, Index())
        self.assertIn("No matching pages found.", output.getvalue())

    def test_find_command_prints_did_you_mean_for_typo(self):
        # Indexed vocabulary contains "indifference"; the user typed
        # "indiference" (one missing 'f'). The CLI must surface the
        # "Did you mean" hint after the zero-results line.
        index = Index(
            documents={0: "page-1"},
            postings={
                "indifference": {0: {"frequency": 1, "positions": [0]}},
            },
        )
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command("find indiference", index)

        text = output.getvalue()
        self.assertIn("No matching pages found.", text)
        self.assertIn("Did you mean: indifference?", text)

    def test_find_command_suppresses_did_you_mean_when_query_is_valid(self):
        # Both tokens are in the vocabulary — zero results here is a
        # strict-AND miss, not a typo. A "did you mean" hint would
        # mislead, so it must be suppressed.
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={
                "good": {0: {"frequency": 1, "positions": [0]}},
                "friends": {1: {"frequency": 1, "positions": [0]}},
            },
        )
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command("find good friends", index)

        text = output.getvalue()
        self.assertIn("No matching pages found.", text)
        self.assertNotIn("Did you mean", text)

    def test_find_command_suppresses_did_you_mean_when_no_candidate_exists(self):
        # Unknown token but no near-neighbour in the vocabulary —
        # nothing useful to suggest, stay silent.
        index = Index(
            documents={0: "page-1"},
            postings={
                "indifference": {0: {"frequency": 1, "positions": [0]}},
            },
        )
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command("find xyzqq", index)

        text = output.getvalue()
        self.assertIn("No matching pages found.", text)
        self.assertNotIn("Did you mean", text)

    def test_find_command_did_you_mean_also_fires_for_phrase_mode(self):
        # The quoted-string phrase path uses the same zero-result
        # handler, so the suggestion hint must surface there too.
        index = Index(
            documents={0: "page-1"},
            postings={
                "indifference": {0: {"frequency": 1, "positions": [0]}},
            },
        )
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command('find "indiference"', index)

        text = output.getvalue()
        self.assertIn("Did you mean: indifference?", text)

    def test_load_command_returns_loaded_index(self):
        loaded_index = Index(
            documents={0: "page-1"},
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
        )
        output = io.StringIO()

        with patch("src.main.load_index", return_value=loaded_index) as load_index:
            with redirect_stdout(output):
                returned_index = handle_command("load", Index())

        self.assertEqual(returned_index, loaded_index)
        load_index.assert_called_once()
        self.assertIn("Loaded index", output.getvalue())

    def test_build_command_crawls_indexes_and_saves(self):
        pages = [CrawledPage(url="page-1", text="good friends")]
        built_index = Index(
            documents={0: "page-1"},
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
        )
        crawler = Mock()
        crawler.crawl.return_value = pages
        output = io.StringIO()

        with patch("src.main.RobotsPolicy.from_url", return_value=Mock()):
            with patch("src.main.QuoteCrawler", return_value=crawler):
                with patch("src.main.build_index", return_value=built_index) as build_index:
                    with patch("src.main.save_index") as save_index:
                        with redirect_stdout(output):
                            returned_index = handle_command("build", Index())

        self.assertEqual(returned_index, built_index)
        build_index.assert_called_once_with(pages)
        save_index.assert_called_once()
        self.assertIn("Built index", output.getvalue())

    def test_build_command_fetches_robots_policy_for_target_site(self):
        crawler = Mock()
        crawler.crawl.return_value = []
        policy = Mock()

        with patch("src.main.RobotsPolicy.from_url", return_value=policy) as from_url:
            with patch("src.main.QuoteCrawler", return_value=crawler) as quote_crawler:
                with patch("src.main.build_index", return_value=Index()):
                    with patch("src.main.save_index"):
                        with redirect_stdout(io.StringIO()):
                            handle_command("build", Index())

        from_url.assert_called_once()
        self.assertEqual(from_url.call_args.args[0], "https://quotes.toscrape.com/")
        self.assertIs(quote_crawler.call_args.kwargs["robots_policy"], policy)


class EnsureUtf8OutputTests(unittest.TestCase):
    def test_reconfigures_non_utf8_streams_to_utf8(self):
        class FakeStream:
            def __init__(self, encoding):
                self.encoding = encoding
                self.reconfigured_with = None

            def reconfigure(self, **kwargs):
                self.reconfigured_with = kwargs

        cp1252 = FakeStream("cp1252")
        already_utf8 = FakeStream("utf-8")

        with patch("src.main.sys.stdout", cp1252), patch("src.main.sys.stderr", already_utf8):
            _ensure_utf8_output()

        self.assertEqual(
            cp1252.reconfigured_with,
            {"encoding": "utf-8", "errors": "replace"},
        )
        # Already-UTF-8 streams are left alone so we don't trigger
        # spurious reconfigure calls on platforms where the operation
        # is a no-op or worse, error-prone.
        self.assertIsNone(already_utf8.reconfigured_with)

    def test_safely_skips_streams_without_reconfigure_method(self):
        class LegacyStream:
            encoding = "cp1252"
            # Older or replaced streams may not expose reconfigure();
            # the helper must tolerate that without raising.

        legacy = LegacyStream()

        with patch("src.main.sys.stdout", legacy), patch("src.main.sys.stderr", legacy):
            # Must not raise.
            _ensure_utf8_output()

    def test_swallows_exceptions_raised_by_reconfigure(self):
        class HostileStream:
            encoding = "cp1252"

            def reconfigure(self, **kwargs):
                raise RuntimeError("stream is detached")

        hostile = HostileStream()

        with patch("src.main.sys.stdout", hostile), patch("src.main.sys.stderr", hostile):
            # Must not propagate the RuntimeError; CLI startup never
            # blocks on a cosmetic concern.
            _ensure_utf8_output()


if __name__ == "__main__":
    unittest.main()
