import unittest

from src.parser import ParsedFields, parse_html_to_fields, parse_html_to_text


class ParseHtmlToTextTests(unittest.TestCase):
    def test_extracts_visible_body_text(self):
        html = "<html><body><p>Hello world.</p></body></html>"

        self.assertEqual(parse_html_to_text(html), "Hello world.")

    def test_returns_empty_string_for_empty_html(self):
        self.assertEqual(parse_html_to_text("<html></html>"), "")

    def test_excludes_script_content(self):
        html = """
        <html>
          <body>
            <script>var secret = 'no';</script>
            <p>Visible.</p>
          </body>
        </html>
        """

        result = parse_html_to_text(html)

        self.assertIn("Visible.", result)
        self.assertNotIn("secret", result)
        self.assertNotIn("var", result)

    def test_excludes_style_content(self):
        html = """
        <html>
          <head><style>.hidden { display: none; }</style></head>
          <body><p>Visible.</p></body>
        </html>
        """

        result = parse_html_to_text(html)

        self.assertIn("Visible.", result)
        self.assertNotIn("hidden", result)
        self.assertNotIn("display", result)

    def test_combines_multiple_text_nodes_with_separator(self):
        html = """
        <html>
          <body>
            <p>First.</p>
            <p>Second.</p>
            <p>Third.</p>
          </body>
        </html>
        """

        self.assertEqual(parse_html_to_text(html), "First. Second. Third.")

    def test_falls_back_to_whole_document_when_no_body(self):
        html = "<html><div>No body tag.</div></html>"

        self.assertEqual(parse_html_to_text(html), "No body tag.")


class ParseHtmlToFieldsTests(unittest.TestCase):
    def test_extracts_title_from_title_tag(self):
        html = "<html><head><title>Quotes to Scrape</title></head><body></body></html>"

        fields = parse_html_to_fields(html)

        self.assertEqual(fields.title, "Quotes to Scrape")

    def test_extracts_quote_texts_in_document_order(self):
        html = """
        <html><body>
          <div class="quote"><span class="text">"First."</span></div>
          <div class="quote"><span class="text">"Second."</span></div>
        </body></html>
        """

        fields = parse_html_to_fields(html)

        self.assertEqual(fields.quote_texts, ['"First."', '"Second."'])

    def test_extracts_authors_from_listing_pages(self):
        html = """
        <html><body>
          <div class="quote"><span><small class="author">Einstein</small></span></div>
          <div class="quote"><span><small class="author">Twain</small></span></div>
        </body></html>
        """

        fields = parse_html_to_fields(html)

        self.assertEqual(fields.authors, ["Einstein", "Twain"])

    def test_extracts_author_title_from_author_detail_page(self):
        html = """
        <html><body>
          <h3 class="author-title">Albert Einstein</h3>
          <p class="author-born-date">March 14, 1879</p>
        </body></html>
        """

        fields = parse_html_to_fields(html)

        self.assertEqual(fields.authors, ["Albert Einstein"])

    def test_extracts_tags_from_quote_blocks(self):
        html = """
        <html><body>
          <div class="quote">
            <div class="tags">
              <a class="tag">love</a>
              <a class="tag">life</a>
            </div>
          </div>
        </body></html>
        """

        fields = parse_html_to_fields(html)

        self.assertEqual(fields.tags, ["love", "life"])

    def test_body_contains_all_visible_text(self):
        html = "<html><body><p>Hello world.</p></body></html>"

        fields = parse_html_to_fields(html)

        self.assertEqual(fields.body, "Hello world.")

    def test_returns_empty_fields_for_empty_html(self):
        fields = parse_html_to_fields("<html></html>")

        self.assertEqual(fields.title, "")
        self.assertEqual(fields.quote_texts, [])
        self.assertEqual(fields.authors, [])
        self.assertEqual(fields.tags, [])
        self.assertEqual(fields.body, "")

    def test_parsed_fields_default_constructs_to_empty(self):
        fields = ParsedFields()

        self.assertEqual(fields.title, "")
        self.assertEqual(fields.quote_texts, [])
        self.assertEqual(fields.authors, [])
        self.assertEqual(fields.tags, [])
        self.assertEqual(fields.body, "")


if __name__ == "__main__":
    unittest.main()
