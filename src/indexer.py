"""Build and persist an inverted index."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from src.crawler import CrawledPage

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9']+")

Posting = dict[str, object]
InvertedIndex = dict[str, dict[str, Posting]]


def tokenize(text: str) -> list[str]:
    """Convert text into case-insensitive searchable tokens."""
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def build_index(pages: Iterable[CrawledPage]) -> InvertedIndex:
    """Create an inverted index from crawled pages."""
    index: InvertedIndex = {}

    for page in pages:
        for position, token in enumerate(tokenize(page.text)):
            page_entry = index.setdefault(token, {}).setdefault(
                page.url,
                {"frequency": 0, "positions": []},
            )
            page_entry["frequency"] = int(page_entry["frequency"]) + 1
            positions = page_entry["positions"]
            if isinstance(positions, list):
                positions.append(position)

    return index


def save_index(index: InvertedIndex, path: str | Path = "data/index.json") -> None:
    """Save the inverted index as JSON."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")


def load_index(path: str | Path = "data/index.json") -> InvertedIndex:
    """Load a previously saved inverted index."""
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Index file not found: {input_path}")
    return json.loads(input_path.read_text(encoding="utf-8"))
