"""Crawler for quotes.toscrape.com."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.robots import RobotsPolicy

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
        robots_policy: RobotsPolicy | None = None,
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
        # Default to a permissive policy so that unit tests and direct uses
        # of the crawler don't trigger network calls; production callers
        # build a real policy with RobotsPolicy.from_text/from_url.
        self.robots_policy = robots_policy if robots_policy is not None else RobotsPolicy.permissive()
        self._sleep = sleep
        self._progress_callback = progress_callback

    def crawl(self, max_pages: int | None = None) -> list[CrawledPage]:
        """Crawl pages reachable from the start URL using BFS over the link graph.

        Implements the seeds → frontier → fetch → parse-for-links loop from
        Lecture 9. The frontier is a FIFO queue of ``(url, depth)`` pairs, so
        pages are visited in breadth-first order. ``max_depth`` (set on the
        crawler) bounds how far we descend; ``max_pages`` bounds how many
        pages we collect per call.
        """
        pages: list[CrawledPage] = []
        visited: set[str] = set()
        frontier: deque[tuple[str, int]] = deque()
        frontier.append((self.start_url, 0))

        # Effective delay honours both the brief's 6-second floor and any
        # Crawl-delay declared in robots.txt — whichever is larger wins.
        crawl_delay = self.robots_policy.crawl_delay()
        effective_delay = max(self.politeness_delay, crawl_delay or 0.0)

        while frontier:
            if max_pages is not None and len(pages) >= max_pages:
                break

            url, depth = frontier.popleft()
            if url in visited:
                continue
            if not self.robots_policy.is_allowed(url):
                self._report(f"Skipping disallowed URL: {url}")
                visited.add(url)
                continue

            if pages:
                self._report(f"Waiting {effective_delay:.0f} seconds before next request...")
                self._sleep(effective_delay)

            self._report(f"Crawling {url}")
            html = self._fetch(url)
            page = self._parse_page(url, html)
            pages.append(page)
            visited.add(url)
            self._report(f"Collected page {len(pages)}: {page.url}")

            if self.max_depth is None or depth < self.max_depth:
                for link in self._extract_links(url, html):
                    if link not in visited:
                        frontier.append((link, depth + 1))

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

    def _parse_page(self, url: str, html: str) -> CrawledPage:
        soup = BeautifulSoup(html, "html.parser")
        quotes = [quote.get_text(" ", strip=True) for quote in soup.select(".quote .text")]
        return CrawledPage(url=url, text=" ".join(quotes))

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
