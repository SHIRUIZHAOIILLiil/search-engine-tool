"""Robots.txt policy enforcement (Lecture 9: the robots.txt file).

Wraps :class:`urllib.robotparser.RobotFileParser` so the rest of the
crawler can ask simple questions ("am I allowed to fetch this URL?",
"how long should I wait between requests to this site?") without
depending on the standard library type directly.
"""

from __future__ import annotations

from urllib.robotparser import RobotFileParser


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

    def is_allowed(self, url: str) -> bool:
        """Return True if the user agent is allowed to fetch ``url``."""
        return self._parser.can_fetch(self._user_agent, url)

    def crawl_delay(self) -> float | None:
        """Return the declared Crawl-delay in seconds, or None if absent."""
        delay = self._parser.crawl_delay(self._user_agent)
        if delay is None:
            return None
        return float(delay)
