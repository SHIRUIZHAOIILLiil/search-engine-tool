import unittest

from src.crawler import QuoteCrawler


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


if __name__ == "__main__":
    unittest.main()
