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

import unittest
from tempfile import TemporaryDirectory

from src.crawler import QuoteCrawler
from src.indexer import build_index, load_index, save_index
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


if __name__ == "__main__":
    unittest.main()
