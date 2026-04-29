"""Crawler for quotes.toscrape.com."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


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
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.start_url = start_url
        self.politeness_delay = politeness_delay
        self.timeout = timeout
        self._sleep = sleep

    def crawl(self, max_pages: int | None = None) -> list[CrawledPage]:
        """Crawl quote pages and return their quote text."""
        pages: list[CrawledPage] = []
        next_url: str | None = self.start_url
        visited: set[str] = set()

        while next_url and next_url not in visited:
            if max_pages is not None and len(pages) >= max_pages:
                break

            if pages:
                self._sleep(self.politeness_delay)

            html = self._fetch(next_url)
            page, next_url = self._parse_page(next_url, html)
            pages.append(page)
            visited.add(page.url)

        return pages

    def _fetch(self, url: str) -> str:
        try:
            response = requests.get(url, timeout=self.timeout)
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


def crawl_site(start_url: str = "https://quotes.toscrape.com/") -> Iterable[CrawledPage]:
    """Convenience wrapper used by the command-line application."""
    return QuoteCrawler(start_url=start_url).crawl()
