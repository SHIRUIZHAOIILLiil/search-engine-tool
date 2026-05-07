"""HTML parsing for the search engine, per Lecture 11.

Implements the second of Lecture 11's two-pass tokenisation strategy:
BeautifulSoup performs the first (markup) pass, and this module
extracts the visible text content that the indexer will tokenise.
Script, style, and other non-content elements are dropped here so the
inverted index does not absorb JavaScript identifiers or CSS rules.
"""

from __future__ import annotations

from bs4 import BeautifulSoup


def parse_html_to_text(html: str) -> str:
    """Return all visible text of an HTML document as a single string.

    The returned string concatenates every text node under ``<body>``
    (or the whole document when no ``<body>`` exists) using a single
    space separator. ``<script>`` and ``<style>`` subtrees are removed
    before extraction so they never reach the index.
    """
    soup = BeautifulSoup(html, "html.parser")
    for non_content in soup(["script", "style"]):
        non_content.decompose()
    body = soup.body or soup
    return body.get_text(" ", strip=True)
