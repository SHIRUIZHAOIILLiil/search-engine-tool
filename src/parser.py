"""HTML parsing for the search engine, per Lecture 11.

Implements the second of Lecture 11's two-pass tokenisation strategy:
BeautifulSoup performs the first (markup) pass, and this module
extracts the visible text content that the indexer will tokenise.
Script, style, and other non-content elements are dropped here so the
inverted index does not absorb JavaScript identifiers or CSS rules.

Selectors are tuned for quotes.toscrape.com — the target site for the
COMP3011 coursework — but the design separates structural fields
(title, quote text, author, tags) from the raw body so a future ranker
can weight them differently (Lecture 11: "main heading... is more
important than the body").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ParsedFields:
    """Per-field text content of a single page.

    ``body`` is the catch-all visible text (equivalent to
    :func:`parse_html_to_text`). The other fields capture site-specific
    structure that downstream ranking/indexing can weight independently.
    """

    title: str = ""
    quote_texts: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    body: str = ""


def parse_html_to_fields(html: str) -> ParsedFields:
    """Parse HTML into a :class:`ParsedFields` with per-field text."""
    soup = BeautifulSoup(html, "html.parser")
    for non_content in soup(["script", "style"]):
        non_content.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    quote_texts = [
        element.get_text(" ", strip=True)
        for element in soup.select(".quote .text")
    ]
    # Author appears as <small class="author"> on listing pages and as
    # <h3 class="author-title"> on /author/<slug>/ detail pages.
    authors = [
        element.get_text(strip=True)
        for element in soup.select(".quote .author, h3.author-title")
    ]
    tags = [
        element.get_text(strip=True)
        for element in soup.select(".quote .tag")
    ]

    body_root = soup.body or soup
    body = body_root.get_text(" ", strip=True)

    return ParsedFields(
        title=title,
        quote_texts=quote_texts,
        authors=authors,
        tags=tags,
        body=body,
    )


def parse_html_to_text(html: str) -> str:
    """Return all visible text of an HTML document as a single string.

    Convenience wrapper around :func:`parse_html_to_fields` that yields
    only the ``body`` field; kept as a separate entry point so callers
    that don't need structure aren't forced to construct a dataclass.
    """
    return parse_html_to_fields(html).body
