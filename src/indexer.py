"""Build and persist an inverted index."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from src.crawler import CrawledPage

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9']+")
INDEX_VERSION = 1

Posting = dict[str, object]
PostingsByUrl = dict[str, dict[str, Posting]]


@dataclass
class Index:
    """Versioned inverted index (Lecture 12 terminology).

    ``version`` is a schema sentinel so :func:`load_index` can reject
    files written by an incompatible schema instead of silently producing
    garbage. ``data`` is the term → URL → posting mapping; a later commit
    will swap the URL keys for integer document ids and add a separate
    document-id ↔ URL map per Lecture 12 ("each page is given a unique
    number to make it more efficient for storing document pointers").
    """

    version: int = INDEX_VERSION
    data: PostingsByUrl = field(default_factory=dict)


def tokenize(text: str) -> list[str]:
    """Convert text into case-insensitive searchable tokens."""
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def build_index(pages: Iterable[CrawledPage]) -> Index:
    """Create an inverted index from crawled pages."""
    index = Index()

    for page in pages:
        for position, token in enumerate(tokenize(page.text)):
            posting = index.data.setdefault(token, {}).setdefault(
                page.url,
                {"frequency": 0, "positions": []},
            )
            posting["frequency"] = int(posting["frequency"]) + 1
            positions = posting["positions"]
            if isinstance(positions, list):
                positions.append(position)

    return index


def save_index(index: Index, path: str | Path = "data/index.json") -> None:
    """Save the inverted index as JSON with its schema version."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": index.version, "data": index.data}
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_index(path: str | Path = "data/index.json") -> Index:
    """Load a previously saved inverted index, validating its schema."""
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Index file not found: {input_path}")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "version" not in payload:
        raise ValueError(
            f"Index file at {input_path} is missing a version field; "
            f"rebuild it with the build command."
        )
    if payload["version"] != INDEX_VERSION:
        raise ValueError(
            f"Index file at {input_path} is version {payload['version']}; "
            f"this tool expects version {INDEX_VERSION}. Rebuild with build."
        )
    return Index(version=payload["version"], data=payload.get("data", {}))
