import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from src.crawler import CrawledPage
from src.main import handle_command


class MainCommandTests(unittest.TestCase):
    def test_help_command_prints_available_commands(self):
        output = io.StringIO()

        with redirect_stdout(output):
            returned_index = handle_command("help", {})

        self.assertEqual(returned_index, {})
        self.assertIn("build", output.getvalue())
        self.assertIn("find <query>", output.getvalue())

    def test_unknown_command_raises_value_error(self):
        with self.assertRaises(ValueError):
            handle_command("unknown", {})

    def test_exit_command_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            handle_command("exit", {})

    def test_quit_command_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            handle_command("quit", {})

    def test_print_command_requires_word_argument(self):
        with self.assertRaises(ValueError):
            handle_command("print", {})

    def test_find_command_requires_query_argument(self):
        with self.assertRaises(ValueError):
            handle_command("find", {})

    def test_print_command_outputs_posting_list(self):
        index = {"good": {"page-1": {"frequency": 1, "positions": [0]}}}
        output = io.StringIO()

        with redirect_stdout(output):
            returned_index = handle_command("print good", index)

        self.assertIs(returned_index, index)
        self.assertIn('"frequency": 1', output.getvalue())
        self.assertIn('"page-1"', output.getvalue())

    def test_find_command_outputs_matching_pages(self):
        index = {
            "good": {"page-1": {"frequency": 1, "positions": [0]}},
            "friends": {"page-1": {"frequency": 1, "positions": [1]}},
        }
        output = io.StringIO()

        with redirect_stdout(output):
            returned_index = handle_command("find good friends", index)

        self.assertIs(returned_index, index)
        self.assertIn("page-1", output.getvalue())

    def test_find_command_reports_no_matches(self):
        output = io.StringIO()

        with redirect_stdout(output):
            returned_index = handle_command("find missing", {})

        self.assertEqual(returned_index, {})
        self.assertIn("No matching pages found.", output.getvalue())

    def test_load_command_returns_loaded_index(self):
        loaded_index = {"good": {"page-1": {"frequency": 1, "positions": [0]}}}
        output = io.StringIO()

        with patch("src.main.load_index", return_value=loaded_index) as load_index:
            with redirect_stdout(output):
                returned_index = handle_command("load", {})

        self.assertEqual(returned_index, loaded_index)
        load_index.assert_called_once()
        self.assertIn("Loaded index", output.getvalue())

    def test_build_command_crawls_indexes_and_saves(self):
        pages = [CrawledPage(url="page-1", text="good friends")]
        built_index = {"good": {"page-1": {"frequency": 1, "positions": [0]}}}
        crawler = Mock()
        crawler.crawl.return_value = pages
        output = io.StringIO()

        with patch("src.main.QuoteCrawler", return_value=crawler):
            with patch("src.main.build_index", return_value=built_index) as build_index:
                with patch("src.main.save_index") as save_index:
                    with redirect_stdout(output):
                        returned_index = handle_command("build", {})

        self.assertEqual(returned_index, built_index)
        build_index.assert_called_once_with(pages)
        save_index.assert_called_once()
        self.assertIn("Built index", output.getvalue())


if __name__ == "__main__":
    unittest.main()
