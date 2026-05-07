"""Build and persist an inverted index."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from src.crawler import CrawledPage

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9']+")
INDEX_VERSION = 2

Posting = dict[str, object]
PostingsByDocId = dict[str, dict[int, Posting]]


@dataclass
class Index:
    """Versioned inverted index keyed by integer document ids (Lecture 12).

    Lecture 12 (slide "Index structure and terminology") prescribes a
    two-table layout for production-grade inverted indices:

    * ``documents`` maps each integer doc_id to its source URL.
    * ``postings`` maps each term to a doc_id-keyed posting list.

    Storing integer doc_ids keeps posting lists compact (a 50-char URL
    would otherwise repeat for every term that appears in the page) and
    enables compressed binary representations later (vbyte / delta
    encoding work on integer streams).

    ``version`` is a schema sentinel so :func:`load_index` can reject
    files written by an incompatible schema instead of silently
    producing garbage.
    """

    version: int = INDEX_VERSION
    documents: dict[int, str] = field(default_factory=dict)
    postings: PostingsByDocId = field(default_factory=dict)


def tokenize(text: str) -> list[str]:
    """Convert text into case-insensitive searchable tokens."""
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def build_index(pages: Iterable[CrawledPage]) -> Index:
    """Create an inverted index from crawled pages.

    Each page receives a sequential integer doc_id on first sight; if
    the same URL appears more than once, the existing doc_id is reused
    so positions accumulate against a single document entry.
    """
    index = Index()
    url_to_doc_id: dict[str, int] = {}

    for page in pages:
        doc_id = url_to_doc_id.get(page.url)
        if doc_id is None:
            doc_id = len(index.documents)
            index.documents[doc_id] = page.url
            url_to_doc_id[page.url] = doc_id
        for position, token in enumerate(tokenize(page.text)):
            posting = index.postings.setdefault(token, {}).setdefault(
                doc_id,
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
    payload = {
        "version": index.version,
        # JSON keys must be strings, so integer doc_ids are stringified
        # here and converted back on load. This stays internal to the
        # serialiser; in-memory keys are always integers.
        "documents": {str(doc_id): url for doc_id, url in index.documents.items()},
        "postings": {
            term: {str(doc_id): posting for doc_id, posting in postings.items()}
            for term, postings in index.postings.items()
        },
    }
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
    documents = {
        int(doc_id): url for doc_id, url in payload.get("documents", {}).items()
    }
    postings = {
        term: {int(doc_id): posting for doc_id, posting in posting_map.items()}
        for term, posting_map in payload.get("postings", {}).items()
    }
    return Index(version=payload["version"], documents=documents, postings=postings)
