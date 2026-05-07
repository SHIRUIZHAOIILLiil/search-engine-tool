"""Robots.txt policy enforcement (Lecture 9: the robots.txt file).

Wraps :class:`urllib.robotparser.RobotFileParser` so the rest of the
crawler can ask simple questions ("am I allowed to fetch this URL?",
"how long should I wait between requests to this site?") without
depending on the standard library type directly.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests


class RobotsPolicy:
    """A parsed robots.txt for a single site, scoped to one user agent."""

    def __init__(self, parser: RobotFileParser, user_agent: str) -> None:
        self._parser = parser
        self._user_agent = user_agent

    @classmethod
    def permissive(cls, user_agent: str = "*") -> "RobotsPolicy":
        """Return a policy that allows every URL and declares no crawl delay.

        Used as a safe default when a site has no robots.txt, when tests
        don't care about robots rules, or before a real policy has been
        loaded for the site.
        """
        parser = RobotFileParser()
        parser.parse([])
        return cls(parser, user_agent)

    @classmethod
    def from_text(cls, robots_txt: str, user_agent: str) -> "RobotsPolicy":
        """Build a policy by parsing raw robots.txt content."""
        parser = RobotFileParser()
        parser.parse(robots_txt.splitlines())
        return cls(parser, user_agent)

    @classmethod
    def from_url(
        cls,
        start_url: str,
        user_agent: str,
        fetch: Callable[[str], str] | None = None,
    ) -> "RobotsPolicy":
        """Fetch ``/robots.txt`` from the start URL's host and parse it.

        Per the robots.txt specification, an unreachable robots.txt is
        equivalent to "no restrictions", so any fetch failure (network
        error, 404, malformed response, etc.) falls back to a permissive
        policy. The ``fetch`` parameter is for injecting a stub in tests;
        production callers leave it as None to use the default HTTP fetch.
        """
        if fetch is None:
            def fetch(url: str) -> str:
                response = requests.get(
                    url,
                    headers={"User-Agent": user_agent},
                    timeout=10.0,
                )
                response.raise_for_status()
                return response.text

        robots_url = urljoin(start_url, "/robots.txt")
        try:
            text = fetch(robots_url)
        except Exception:
            return cls.permissive(user_agent)
        return cls.from_text(text, user_agent)

    def is_allowed(self, url: str) -> bool:
        """Return True if the user agent is allowed to fetch ``url``."""
        return self._parser.can_fetch(self._user_agent, url)

    def crawl_delay(self) -> float | None:
        """Return the declared Crawl-delay in seconds, or None if absent."""
        delay = self._parser.crawl_delay(self._user_agent)
        if delay is None:
            return None
        return float(delay)
