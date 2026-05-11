import unittest
from unittest.mock import Mock, patch

import requests

from src.crawler import DEFAULT_USER_AGENT, CrawlerError, QuoteCrawler
from src.robots import RobotsPolicy


class QuoteCrawlerTests(unittest.TestCase):
    def test_parse_page_extracts_quotes(self):
        html = """
        <html>
          <div class="quote"><span class="text">First quote.</span></div>
          <div class="quote"><span class="text">Second quote.</span></div>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page = crawler._parse_page("https://quotes.toscrape.com/", html)

        self.assertEqual(page.url, "https://quotes.toscrape.com/")
        self.assertIn("First quote.", page.text)
        self.assertIn("Second quote.", page.text)

    def test_parse_page_handles_page_without_quotes(self):
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page = crawler._parse_page("https://quotes.toscrape.com/", "<html></html>")

        self.assertEqual(page.url, "https://quotes.toscrape.com/")
        self.assertEqual(page.text, "")

    def test_parse_page_extracts_author_and_tag_text(self):
        html = """
        <html>
          <body>
            <div class="quote">
              <span class="text">A quote.</span>
              <span>by <small class="author">Einstein</small></span>
              <div class="tags">
                <a class="tag">science</a>
                <a class="tag">physics</a>
              </div>
            </div>
          </body>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page = crawler._parse_page("https://quotes.toscrape.com/", html)

        self.assertIn("A quote.", page.text)
        self.assertIn("Einstein", page.text)
        self.assertIn("science", page.text)
        self.assertIn("physics", page.text)

    def test_parse_page_excludes_script_and_style_content(self):
        html = """
        <html>
          <head>
            <style>body { color: red; }</style>
          </head>
          <body>
            <script>alert('secret');</script>
            <p>Visible text.</p>
          </body>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page = crawler._parse_page("https://quotes.toscrape.com/", html)

        self.assertIn("Visible text.", page.text)
        self.assertNotIn("color: red", page.text)
        self.assertNotIn("alert", page.text)
        self.assertNotIn("secret", page.text)

    def test_parse_page_attaches_structured_fields_to_crawled_page(self):
        html = """
        <html>
          <head><title>Quotes to Scrape</title></head>
          <body>
            <div class="quote">
              <span class="text">"A quote."</span>
              <span><small class="author">Einstein</small></span>
              <div class="tags"><a class="tag">science</a></div>
            </div>
          </body>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page = crawler._parse_page("https://quotes.toscrape.com/", html)

        self.assertEqual(page.fields.title, "Quotes to Scrape")
        self.assertEqual(page.fields.quote_texts, ['"A quote."'])
        self.assertEqual(page.fields.authors, ["Einstein"])
        self.assertEqual(page.fields.tags, ["science"])
        # text remains the concatenated body for backward compatibility.
        self.assertEqual(page.text, page.fields.body)

    def test_parse_page_combines_multiple_quotes_in_order(self):
        html = """
        <html>
          <div class="quote"><span class="text">First quote.</span></div>
          <div class="quote"><span class="text">Second quote.</span></div>
          <div class="quote"><span class="text">Third quote.</span></div>
        </html>
        """
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/")

        page = crawler._parse_page("https://quotes.toscrape.com/", html)

        self.assertEqual(page.text, "First quote. Second quote. Third quote.")

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
        self.assertIn("First page.", pages[0].text)
        self.assertIn("Second page.", pages[1].text)

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

    def test_crawl_traverses_in_bfs_order(self):
        html_by_url = {
            "https://quotes.toscrape.com/": """
                <a href="/page/A/">A</a>
                <a href="/page/B/">B</a>
            """,
            "https://quotes.toscrape.com/page/A/": """
                <a href="/page/A1/">A1</a>
            """,
            "https://quotes.toscrape.com/page/B/": """
                <a href="/page/B1/">B1</a>
            """,
            "https://quotes.toscrape.com/page/A1/": "",
            "https://quotes.toscrape.com/page/B1/": "",
        }
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/", sleep=lambda _: None)
        crawler._fetch = lambda url: html_by_url[url]

        pages = crawler.crawl()

        self.assertEqual(
            [page.url for page in pages],
            [
                "https://quotes.toscrape.com/",
                "https://quotes.toscrape.com/page/A/",
                "https://quotes.toscrape.com/page/B/",
                "https://quotes.toscrape.com/page/A1/",
                "https://quotes.toscrape.com/page/B1/",
            ],
        )

    def test_crawl_skips_already_visited_urls(self):
        html_by_url = {
            "https://quotes.toscrape.com/": '<a href="/B/">B</a>',
            "https://quotes.toscrape.com/B/": '<a href="https://quotes.toscrape.com/">Back</a>',
        }
        crawler = QuoteCrawler(start_url="https://quotes.toscrape.com/", sleep=lambda _: None)
        crawler._fetch = lambda url: html_by_url[url]

        pages = crawler.crawl()

        self.assertEqual(
            [page.url for page in pages],
            [
                "https://quotes.toscrape.com/",
                "https://quotes.toscrape.com/B/",
            ],
        )

    def test_crawl_respects_max_depth(self):
        html_by_url = {
            "https://quotes.toscrape.com/": '<a href="/A/">A</a>',
            "https://quotes.toscrape.com/A/": '<a href="/A1/">A1</a>',
            "https://quotes.toscrape.com/A1/": '<a href="/A2/">A2</a>',
        }
        crawler = QuoteCrawler(
            start_url="https://quotes.toscrape.com/",
            max_depth=1,
            sleep=lambda _: None,
        )
        crawler._fetch = lambda url: html_by_url[url]

        pages = crawler.crawl()

        self.assertEqual(
            [page.url for page in pages],
            [
                "https://quotes.toscrape.com/",
                "https://quotes.toscrape.com/A/",
            ],
        )

    def test_default_robots_policy_is_permissive(self):
        crawler = QuoteCrawler(start_url="https://example.com/")

        self.assertTrue(crawler.robots_policy.is_allowed("https://example.com/anything"))
        self.assertIsNone(crawler.robots_policy.crawl_delay())

    def test_crawl_skips_urls_disallowed_by_robots(self):
        robots_txt = "User-agent: *\nDisallow: /private/\n"
        policy = RobotsPolicy.from_text(robots_txt, DEFAULT_USER_AGENT)

        html_by_url = {
            "https://quotes.toscrape.com/": (
                '<a href="/private/secret/">Private</a>'
                '<a href="/public/">Public</a>'
            ),
            "https://quotes.toscrape.com/public/": "",
        }
        crawler = QuoteCrawler(
            start_url="https://quotes.toscrape.com/",
            robots_policy=policy,
            sleep=lambda _: None,
        )
        crawler._fetch = lambda url: html_by_url[url]

        pages = crawler.crawl()

        urls = [page.url for page in pages]
        self.assertIn("https://quotes.toscrape.com/", urls)
        self.assertIn("https://quotes.toscrape.com/public/", urls)
        self.assertNotIn("https://quotes.toscrape.com/private/secret/", urls)

    def test_crawl_uses_robots_crawl_delay_when_larger_than_politeness(self):
        robots_txt = "User-agent: *\nCrawl-delay: 10\n"
        policy = RobotsPolicy.from_text(robots_txt, DEFAULT_USER_AGENT)

        html_by_url = {
            "https://example.com/": '<a href="/page2/">Next</a>',
            "https://example.com/page2/": "",
        }
        waits: list[float] = []
        crawler = QuoteCrawler(
            start_url="https://example.com/",
            politeness_delay=6.0,
            robots_policy=policy,
            sleep=waits.append,
        )
        crawler._fetch = lambda url: html_by_url[url]

        crawler.crawl()

        self.assertEqual(waits, [10.0])

    def test_crawl_keeps_politeness_when_robots_delay_is_smaller(self):
        robots_txt = "User-agent: *\nCrawl-delay: 2\n"
        policy = RobotsPolicy.from_text(robots_txt, DEFAULT_USER_AGENT)

        html_by_url = {
            "https://example.com/": '<a href="/page2/">Next</a>',
            "https://example.com/page2/": "",
        }
        waits: list[float] = []
        crawler = QuoteCrawler(
            start_url="https://example.com/",
            politeness_delay=6.0,
            robots_policy=policy,
            sleep=waits.append,
        )
        crawler._fetch = lambda url: html_by_url[url]

        crawler.crawl()

        self.assertEqual(waits, [6.0])

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
