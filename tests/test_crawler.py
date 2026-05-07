import unittest

from unittest.mock import Mock, patch

import requests

from src.crawler import DEFAULT_USER_AGENT, CrawlerError, QuoteCrawler


class QuoteCrawlerTests(unittest.TestCase):
    def test_parse_page_extracts_quotes_and_next_link(self):
        html = """
        <html>
          <div class="quote"><span class="text">First quote.</span></div>
          <div class="quote"><span class="text">Second quote.</span></div>
          <li class="next"><a href="/page/2/">Next</a></li>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page, next_url = crawler._parse_page("https://quotes.toscrape.com/", html)

        self.assertEqual(page.url, "https://quotes.toscrape.com/")
        self.assertIn("First quote.", page.text)
        self.assertIn("Second quote.", page.text)
        self.assertEqual(next_url, "https://quotes.toscrape.com/page/2/")

    def test_parse_page_handles_missing_next_link(self):
        html = """
        <html>
          <div class="quote"><span class="text">Only quote.</span></div>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page, next_url = crawler._parse_page("https://quotes.toscrape.com/", html)

        self.assertEqual(page.text, "Only quote.")
        self.assertIsNone(next_url)

    def test_parse_page_handles_page_without_quotes(self):
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page, next_url = crawler._parse_page("https://quotes.toscrape.com/", "<html></html>")

        self.assertEqual(page.url, "https://quotes.toscrape.com/")
        self.assertEqual(page.text, "")
        self.assertIsNone(next_url)

    def test_parse_page_combines_multiple_quotes_in_order(self):
        html = """
        <html>
          <div class="quote"><span class="text">First quote.</span></div>
          <div class="quote"><span class="text">Second quote.</span></div>
          <div class="quote"><span class="text">Third quote.</span></div>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page, next_url = crawler._parse_page("https://quotes.toscrape.com/", html)

        self.assertEqual(page.text, "First quote. Second quote. Third quote.")
        self.assertIsNone(next_url)

    def test_crawl_follows_next_links_without_real_network(self):
        html_by_url = {
            "https://quotes.toscrape.com/": """
                <div class="quote"><span class="text">First page.</span></div>
                <li class="next"><a href="/page/2/">Next</a></li>
            """,
            "https://quotes.toscrape.com/page/2/": """
                <div class="quote"><span class="text">Second page.</span></div>
            """,
        }
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/", sleep=lambda _: None)
        crawler._fetch = lambda url: html_by_url[url]

        pages = crawler.crawl()

        self.assertEqual(
            [page.url for page in pages],
            ["https://quotes.toscrape.com/", "https://quotes.toscrape.com/page/2/"],
        )
        self.assertEqual([page.text for page in pages], ["First page.", "Second page."])

    def test_crawl_waits_between_successive_requests(self):
        html_by_url = {
            "https://quotes.toscrape.com/": """
                <div class="quote"><span class="text">First page.</span></div>
                <li class="next"><a href="/page/2/">Next</a></li>
            """,
            "https://quotes.toscrape.com/page/2/": """
                <div class="quote"><span class="text">Second page.</span></div>
            """,
        }
        waits = []
        crawler = QuoteCrawler(
            start_url="https://quotes.toscrape.com/",
            politeness_delay=6.0,
            sleep=waits.append,
        )
        crawler._fetch = lambda url: html_by_url[url]

        crawler.crawl()

        self.assertEqual(waits, [6.0])

    def test_crawl_respects_max_pages(self):
        html = """
        <div class="quote"><span class="text">First page.</span></div>
        <li class="next"><a href="/page/2/">Next</a></li>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/", sleep=lambda _: None)
        crawler._fetch = Mock(return_value=html)

        pages = crawler.crawl(max_pages=1)

        self.assertEqual(len(pages), 1)
        crawler._fetch.assert_called_once_with("https://quotes.toscrape.com/")

    def test_fetch_wraps_request_errors(self):
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        with patch("src.crawler.requests.get", side_effect=requests.RequestException("network down")):
            with self.assertRaises(CrawlerError):
                crawler._fetch("https://quotes.toscrape.com/")

    def test_fetch_wraps_http_status_errors(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("500 error")
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        with patch("src.crawler.requests.get", return_value=response):
            with self.assertRaises(CrawlerError):
                crawler._fetch("https://quotes.toscrape.com/")

    def test_fetch_sends_default_user_agent_header(self):
        response = Mock()
        response.text = ""
        response.raise_for_status = Mock()
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        with patch("src.crawler.requests.get", return_value=response) as mock_get:
            crawler._fetch("https://quotes.toscrape.com/")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["User-Agent"], DEFAULT_USER_AGENT)

    def test_extract_links_returns_absolute_same_host_links(self):
        html = """
        <html>
          <a href="/page/2/">Next</a>
          <a href="https://quotes.toscrape.com/author/Einstein/">Einstein</a>
          <a href="tag/love/">Love</a>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        links = crawler._extract_links("https://quotes.toscrape.com/", html)

        self.assertEqual(
            links,
            [
                "https://quotes.toscrape.com/page/2/",
                "https://quotes.toscrape.com/author/Einstein/",
                "https://quotes.toscrape.com/tag/love/",
            ],
        )

    def test_extract_links_filters_other_hosts(self):
        html = """
        <html>
          <a href="/page/2/">Next</a>
          <a href="https://example.com/external">External</a>
          <a href="https://other.toscrape.com/elsewhere">Subdomain</a>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        links = crawler._extract_links("https://quotes.toscrape.com/", html)

        self.assertEqual(links, ["https://quotes.toscrape.com/page/2/"])

    def test_extract_links_deduplicates_and_strips_fragments(self):
        html = """
        <html>
          <a href="/page/2/">Next</a>
          <a href="/page/2/#top">Same with fragment</a>
          <a href="/page/2/">Duplicate</a>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        links = crawler._extract_links("https://quotes.toscrape.com/", html)

        self.assertEqual(links, ["https://quotes.toscrape.com/page/2/"])

    def test_extract_links_skips_anchors_without_href(self):
        html = """
        <html>
          <a>No href</a>
          <a href="">Empty</a>
          <a href="/page/2/">Valid</a>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        links = crawler._extract_links("https://quotes.toscrape.com/", html)

        self.assertEqual(links, ["https://quotes.toscrape.com/page/2/"])

    def test_max_depth_defaults_to_none(self):
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        self.assertIsNone(crawler.max_depth)

    def test_max_depth_can_be_set_via_init(self):
        crawler = QuoteCrawler(
            start_url="https://quotes.toscrape.com/",
            max_depth=5,
        )

        self.assertEqual(crawler.max_depth, 5)

    def test_fetch_uses_custom_user_agent_when_provided(self):
        response = Mock()
        response.text = ""
        response.raise_for_status = Mock()
        crawler = QuoteCrawler(
            start_url="https://quotes.toscrape.com/",
            user_agent="MyCustomBot/1.0",
        )

        with patch("src.crawler.requests.get", return_value=response) as mock_get:
            crawler._fetch("https://quotes.toscrape.com/")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["User-Agent"], "MyCustomBot/1.0")


if __name__ == "__main__":
    unittest.main()
