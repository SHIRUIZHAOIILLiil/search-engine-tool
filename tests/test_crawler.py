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


if __name__ == "__main__":
    unittest.main()
