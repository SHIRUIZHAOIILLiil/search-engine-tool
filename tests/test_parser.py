import unittest

from src.parser import parse_html_to_text


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


if __name__ == "__main__":
    unittest.main()
