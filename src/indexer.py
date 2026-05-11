"""Build and persist an inverted index."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, cast

from src.crawler import CrawledPage
from src.parser import ParsedFields
from src.tokenizer import TokenizerConfig, tokenize

INDEX_VERSION = 4

# Names of the structured fields recorded in each posting's ``fields`` map.
# The catch-all ``body`` field is *not* listed here because it is already
# captured by the top-level ``frequency`` / ``positions`` keys; the entries
# below are the additional Lecture 12 "fields and extents" slots that a
# future BM25F-style ranker can weight independently.
FIELD_NAMES: tuple[str, ...] = ("title", "quote_text", "author", "tag")

Posting = dict[str, object]
PostingsByDocId = dict[str, dict[int, Posting]]


@dataclass
class Index:
    """Versioned inverted index keyed by integer document ids (Lecture 12).

    Lecture 12 (slide "Index structure and terminology") prescribes a
    two-table layout for production-grade inverted indices:

    * ``documents`` maps each integer doc_id to its source URL.
    * ``postings`` maps each term to a doc_id-keyed posting list.
    * ``doc_lengths`` records each document's token count, needed by
      length-normalising rankers like BM25 (Croft, Metzler & Strohman,
      ch. 5).
    * ``tokenizer_config`` is the :class:`~src.tokenizer.TokenizerConfig`
      under which this index was built. Storing it on the index means
      :mod:`src.search` can tokenise queries with the same options
      automatically — no need for callers to remember whether stemming
      or stopword filtering were enabled at build time.

    Storing integer doc_ids keeps posting lists compact (a 50-char URL
    would otherwise repeat for every term that appears in the page) and
    enables compressed binary representations later (vbyte / delta
    encoding work on integer streams).

    Each posting contains the body-level ``frequency`` / ``positions``
    plus a ``fields`` map with the same statistics broken down by
    structural field (Lecture 12 "Fields and Extents") so a future
    ranker can apply per-field weights.

    ``version`` is a schema sentinel so :func:`load_index` can reject
    files written by an incompatible schema instead of silently
    producing garbage.
    """

    version: int = INDEX_VERSION
    documents: dict[int, str] = field(default_factory=dict)
    postings: PostingsByDocId = field(default_factory=dict)
    doc_lengths: dict[int, int] = field(default_factory=dict)
    tokenizer_config: TokenizerConfig = field(default_factory=TokenizerConfig)


def build_index(
    pages: Iterable[CrawledPage],
    config: TokenizerConfig | None = None,
) -> Index:
    """Create an inverted index from crawled pages.

    Each page receives a sequential integer doc_id on first sight; if
    the same URL appears more than once, the existing doc_id is reused
    so positions accumulate against a single document entry.

    Tokens are recorded twice: once at the top level (``frequency`` /
    ``positions``) for the body text, matching the brief's "all word
    occurrences" requirement and what ``find_pages`` / ``print_word``
    consume; and once per structural field (``fields[name]``) for
    future BM25F-style ranking.

    The supplied :class:`~src.tokenizer.TokenizerConfig` (or the
    default ``TokenizerConfig()``) governs every ``tokenize`` call in
    this build and is stored on the resulting :class:`Index` so the
    search layer can apply the same config to user queries.
    """
    if config is None:
        config = TokenizerConfig()
    index = Index(tokenizer_config=config)
    url_to_doc_id: dict[str, int] = {}

    for page in pages:
        doc_id = url_to_doc_id.get(page.url)
        if doc_id is None:
            doc_id = len(index.documents)
            index.documents[doc_id] = page.url
            url_to_doc_id[page.url] = doc_id

        # Body pass: feeds the top-level statistics that the brief's
        # print/find commands rely on, and tallies the body token count
        # for length-aware rankers like BM25.
        body_tokens = tokenize(page.text, config)
        index.doc_lengths[doc_id] = (
            index.doc_lengths.get(doc_id, 0) + len(body_tokens)
        )
        for position, token in enumerate(body_tokens):
            posting = index.postings.setdefault(token, {}).setdefault(
                doc_id,
                _empty_posting(),
            )
            # ``Posting`` is typed as ``dict[str, object]`` to fit
            # both ``int`` frequencies and ``list[int]`` positions in
            # one mapping; ``cast`` is the lightest-weight way to
            # restore the int invariant for mypy without a wholesale
            # ``TypedDict`` refactor (queued for v1.7.0).
            posting["frequency"] = cast(int, posting["frequency"]) + 1
            positions = posting["positions"]
            if isinstance(positions, list):
                positions.append(position)

        # Per-field pass: independent tokenisation per structural slot.
        # A token that appears in a field but never in the body still
        # produces a posting (frequency=0 at top level) so that future
        # field-weighted rankers can reach it.
        for field_name, field_text in _iter_named_fields(page.fields):
            for position, token in enumerate(tokenize(field_text, config)):
                posting = index.postings.setdefault(token, {}).setdefault(
                    doc_id,
                    _empty_posting(),
                )
                fields_map = posting["fields"]
                if not isinstance(fields_map, dict):
                    continue
                field_stats = fields_map.setdefault(
                    field_name,
                    {"frequency": 0, "positions": []},
                )
                field_stats["frequency"] = int(field_stats["frequency"]) + 1
                field_positions = field_stats["positions"]
                if isinstance(field_positions, list):
                    field_positions.append(position)

    return index


def _empty_posting() -> Posting:
    """Return a fresh posting with the canonical key layout."""
    return {"frequency": 0, "positions": [], "fields": {}}


def _iter_named_fields(fields: ParsedFields) -> Iterator[tuple[str, str]]:
    """Yield ``(field_name, joined_text)`` pairs for the named slots.

    ``ParsedFields`` exposes ``quote_texts``, ``authors`` and ``tags`` as
    lists; the indexer treats each list as a single text blob (joined
    with spaces) so positions count tokens within the slot rather than
    within an individual list element.
    """
    yield "title", fields.title
    yield "quote_text", " ".join(fields.quote_texts)
    yield "author", " ".join(fields.authors)
    yield "tag", " ".join(fields.tags)


def save_index(index: Index, path: str | Path = "data/index.json") -> None:
    """Save the inverted index as JSON, atomically.

    Writes the serialised payload to a sibling ``<path>.tmp`` file
    first, then replaces the destination via :func:`os.replace`.
    ``os.replace`` is atomic on POSIX (``rename(2)``) and Windows
    (``MoveFileExW`` with ``MOVEFILE_REPLACE_EXISTING``), so after
    this function returns the file at ``path`` is either the new
    content in full or, if any step before the replace fails, the
    previous content untouched. A crash between write and replace
    leaves a ``.tmp`` orphan but never corrupts ``index.json``.

    This matters for the search tool's recovery story: a power loss
    or Ctrl+C during ``build`` previously left ``data/index.json``
    half-written, which then made ``load`` raise schema errors on
    the next run. With atomic write, ``load`` either gets the prior
    good index or (on first ever build) ``FileNotFoundError`` —
    both recoverable states, neither a corrupt-byte trap.
    """
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
        "doc_lengths": {
            str(doc_id): length for doc_id, length in index.doc_lengths.items()
        },
        "tokenizer_config": asdict(index.tokenizer_config),
    }
    serialised = json.dumps(payload, indent=2, sort_keys=True)

    # Same parent directory so os.replace is a rename (cheap, atomic);
    # crossing filesystems would degrade to copy+unlink and forfeit
    # the atomicity guarantee.
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    tmp_path.write_text(serialised, encoding="utf-8")
    os.replace(tmp_path, output_path)


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
    doc_lengths = {
        int(doc_id): length for doc_id, length in payload.get("doc_lengths", {}).items()
    }
    # Tokeniser config is an additive field — pre-13.2 v4 indexes won't
    # have it on disk, but defaulting matches their build-time behaviour
    # (no stemming, no stopword filter).
    config_data = payload.get("tokenizer_config", {})
    tokenizer_config = TokenizerConfig(**config_data)
    return Index(
        version=payload["version"],
        documents=documents,
        postings=postings,
        doc_lengths=doc_lengths,
        tokenizer_config=tokenizer_config,
    )
