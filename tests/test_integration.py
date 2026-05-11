"""End-to-end integration tests for the search engine pipeline.

Unit tests in the rest of the suite cover each module in isolation.
The tests in this file exercise the **whole pipeline** in one shot:
``QuoteCrawler`` (with a stub HTTP fetch) discovers and fetches a
synthetic three-page site, ``build_index`` produces an in-memory
:class:`~src.indexer.Index`, ``save_index`` / ``load_index`` round-trip
it through a temp file, and ``find_pages`` / ``find_phrase`` /
``print_word`` return user-visible results.

The synthetic site mimics quotes.toscrape.com's structure (a quote, an
``<small class="author">`` byline, ``<a class="tag">`` tags, and a
``Next`` link) so the same parser selectors that drive the real build
also drive these tests.
"""

import io
import unittest
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory

from src.crawler import QuoteCrawler
from src.indexer import build_index, load_index, save_index
from src.main import handle_command
from src.search import find_pages, find_phrase, print_word

# A tiny synthetic site with realistic quotes.toscrape.com markup.
SITE: dict[str, str] = {
    "https://example.com/": """
        <html><head><title>Quotes to Scrape</title></head>
        <body>
          <div class="quote">
            <span class="text">"Good friends are like stars."</span>
            <span>by <small class="author">Anna Sage</small></span>
            <div class="tags">
              <a class="tag">friendship</a>
              <a class="tag">stars</a>
            </div>
          </div>
          <a href="https://example.com/page/2/">Next</a>
        </body></html>
    """,
    "https://example.com/page/2/": """
        <html><head><title>Quotes to Scrape</title></head>
        <body>
          <div class="quote">
            <span class="text">"Good morning, sunshine."</span>
            <span>by <small class="author">Bob Hope</small></span>
            <div class="tags">
              <a class="tag">morning</a>
            </div>
          </div>
          <a href="https://example.com/page/3/">Next</a>
        </body></html>
    """,
    "https://example.com/page/3/": """
        <html><head><title>Quotes to Scrape</title></head>
        <body>
          <div class="quote">
            <span class="text">"Brevity is the soul of wit."</span>
            <span>by <small class="author">William Shakespeare</small></span>
            <div class="tags">
              <a class="tag">brevity</a>
              <a class="tag">wit</a>
            </div>
          </div>
        </body></html>
    """,
}


def _make_crawler() -> QuoteCrawler:
    """Build a crawler whose fetch returns from :data:`SITE`."""
    crawler = QuoteCrawler(
        start_url="https://example.com/",
        sleep=lambda _: None,
    )
    crawler._fetch = lambda url: SITE[url]
    return crawler


class FullPipelineTests(unittest.TestCase):
    def test_bfs_discovers_every_page_linked_from_the_seed(self):
        # The crawler should visit page-1 → page-2 → page-3 via the
        # ``Next`` link chain. No same-host page is missed.
        pages = _make_crawler().crawl()

        urls = {page.url for page in pages}

        self.assertEqual(urls, set(SITE.keys()))

    def test_build_then_find_returns_pages_that_contain_the_query_word(self):
        pages = _make_crawler().crawl()
        index = build_index(pages)

        # "good" appears in pages 1 and 2, not page 3.
        self.assertEqual(
            set(find_pages(index, "good")),
            {"https://example.com/", "https://example.com/page/2/"},
        )

    def test_save_and_load_preserves_search_results(self):
        pages = _make_crawler().crawl()
        index = build_index(pages)
        before = find_pages(index, "good friends")

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"
            save_index(index, path)
            loaded = load_index(path)

        # Round-tripping through JSON must not change what users see.
        self.assertEqual(find_pages(loaded, "good friends"), before)

    def test_phrase_query_distinguishes_phrase_from_conjunctive_match(self):
        pages = _make_crawler().crawl()
        index = build_index(pages)

        # Conjunctive: pages 1 and 2 both contain "good" AND "morning"-
        # related text? Actually only page 2 has both "good" and
        # "morning". So conjunctive "good morning" already narrows to
        # page 2 in this fixture — phrase mode just confirms the
        # adjacency.
        self.assertEqual(
            find_phrase(index, "good morning"),
            ["https://example.com/page/2/"],
        )

        # And "good friends" is a phrase only on page 1.
        self.assertEqual(
            find_phrase(index, "good friends"),
            ["https://example.com/"],
        )

    def test_print_word_surfaces_postings_with_frequency_and_positions(self):
        pages = _make_crawler().crawl()
        index = build_index(pages)

        postings = print_word(index, "good")

        # Two pages mention "good"; both should appear in the postings.
        self.assertIn("https://example.com/", postings)
        self.assertIn("https://example.com/page/2/", postings)
        self.assertNotIn("https://example.com/page/3/", postings)
        # Each posting must expose frequency and positions metadata.
        for url, posting in postings.items():
            with self.subTest(url=url):
                self.assertGreaterEqual(int(posting["frequency"]), 1)
                self.assertIsInstance(posting["positions"], list)


class DidYouMeanPipelineTests(unittest.TestCase):
    """End-to-end coverage of the v1.2.0 spelling-correction hint.

    Unit tests in ``test_search.py`` and ``test_main.py`` already pin
    the suggestion logic against hand-built indices. The tests here
    take the *real* pipeline — stub crawl, parse, build, save, load,
    handle_command — and verify the hint surfaces on a corpus the
    user could plausibly produce with the brief's ``build`` command.
    """

    def test_typo_in_unquoted_query_surfaces_did_you_mean(self):
        # "frends" is one insertion away from "friends" (which appears
        # in the page-1 quote text). The full crawler-to-CLI pipeline
        # must catch that and emit the reformulated query.
        pages = _make_crawler().crawl()
        index = build_index(pages)
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command("find frends", index)

        text = output.getvalue()
        self.assertIn("No matching pages found.", text)
        self.assertIn("Did you mean: friends?", text)

    def test_typo_in_phrase_query_surfaces_did_you_mean(self):
        # Quoted phrases route through find_phrase; the zero-result
        # handler is shared with the conjunctive path, so the hint
        # must also fire here.
        pages = _make_crawler().crawl()
        index = build_index(pages)
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command('find "good frends"', index)

        text = output.getvalue()
        self.assertIn("No matching pages found.", text)
        self.assertIn("Did you mean: good friends?", text)

    def test_did_you_mean_survives_save_load_roundtrip(self):
        # The hint depends on the vocabulary stored in ``Index.postings``.
        # Round-tripping through JSON must not change the vocabulary —
        # if it did, the suggestion would silently degrade after a
        # ``load`` command and we would never notice without this test.
        pages = _make_crawler().crawl()
        index = build_index(pages)

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"
            save_index(index, path)
            loaded = load_index(path)

        output = io.StringIO()
        with redirect_stdout(output):
            handle_command("find frends", loaded)

        self.assertIn("Did you mean: friends?", output.getvalue())

    def test_valid_zero_result_query_stays_silent(self):
        # AND filter has zero results because no page contains both
        # "good" and "shakespeare" — both tokens are legitimate, so
        # the CLI must NOT print "Did you mean" (that would imply
        # the user typo'd, which they did not).
        pages = _make_crawler().crawl()
        index = build_index(pages)
        output = io.StringIO()

        with redirect_stdout(output):
            handle_command("find good shakespeare", index)

        text = output.getvalue()
        self.assertIn("No matching pages found.", text)
        self.assertNotIn("Did you mean", text)


if __name__ == "__main__":
    unittest.main()
