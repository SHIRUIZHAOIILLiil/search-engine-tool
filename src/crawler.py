"""Crawler for quotes.toscrape.com."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Identifies the crawler to web servers (Lecture 9: "User-Agent" HTTP header).
# The "+url" suffix is the conventional way for a crawler to advertise a
# contact / project link so that server administrators can reach the operator.
DEFAULT_USER_AGENT = (
    "COMP3011-SearchTool/0.1 "
    "(+https://github.com/SHIRUIZHAOIILLiil/search-engine-tool)"
)


@dataclass(frozen=True)
class CrawledPage:
    """Text content collected from one crawled page."""

    url: str
    text: str


class CrawlerError(RuntimeError):
    """Raised when a page cannot be crawled."""


class QuoteCrawler:
    """Crawl quote pages while respecting a politeness delay."""

    def __init__(
        self,
        start_url: str = "https://quotes.toscrape.com/",
        politeness_delay: float = 6.0,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_depth: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        # max_depth bounds how far the crawler descends from the seed URLs
        # (Lecture 9: defence against fictitious-resource traps that would
        # otherwise cause infinite recursion). None disables the limit.
        self.start_url = start_url
        self.politeness_delay = politeness_delay
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_depth = max_depth
        self._sleep = sleep
        self._progress_callback = progress_callback

    def crawl(self, max_pages: int | None = None) -> list[CrawledPage]:
        """Crawl quote pages and return their quote text."""
        pages: list[CrawledPage] = []
        next_url: str | None = self.start_url
        visited: set[str] = set()

        while next_url and next_url not in visited:
            if max_pages is not None and len(pages) >= max_pages:
                break

            if pages:
                self._report(f"Waiting {self.politeness_delay:.0f} seconds before next request...")
                self._sleep(self.politeness_delay)

            self._report(f"Crawling {next_url}")
            html = self._fetch(next_url)
            page, next_url = self._parse_page(next_url, html)
            pages.append(page)
            visited.add(page.url)
            self._report(f"Collected page {len(pages)}: {page.url}")

        return pages

    def _fetch(self, url: str) -> str:
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CrawlerError(f"Failed to crawl {url}: {exc}") from exc
        return response.text

    def _parse_page(self, url: str, html: str) -> tuple[CrawledPage, str | None]:
        soup = BeautifulSoup(html, "html.parser")
        quotes = [quote.get_text(" ", strip=True) for quote in soup.select(".quote .text")]
        next_link = soup.select_one("li.next a")
        next_url = urljoin(url, next_link["href"]) if next_link and next_link.get("href") else None
        return CrawledPage(url=url, text=" ".join(quotes)), next_url

    def _extract_links(self, base_url: str, html: str) -> list[str]:
        """Return absolute, deduplicated, same-host links from a page.

        Implements the "parse for link tags" step from Lecture 9's
        crawling-process diagram. Used by the BFS frontier to discover
        new URLs while ignoring fragments, duplicate hrefs, and links
        that leave the start host.
        """
        soup = BeautifulSoup(html, "html.parser")
        base_host = urlparse(base_url).netloc
        seen: set[str] = set()
        links: list[str] = []
        for anchor in soup.select("a[href]"):
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            absolute, _, _ = urljoin(base_url, href).partition("#")
            if not absolute or absolute in seen:
                continue
            if urlparse(absolute).netloc != base_host:
                continue
            seen.add(absolute)
            links.append(absolute)
        return links

    def _report(self, message: str) -> None:
        if self._progress_callback is not None:
            self._progress_callback(message)


def crawl_site(start_url: str = "https://quotes.toscrape.com/") -> Iterable[CrawledPage]:
    """Convenience wrapper used by the command-line application."""
    return QuoteCrawler(start_url=start_url).crawl()
