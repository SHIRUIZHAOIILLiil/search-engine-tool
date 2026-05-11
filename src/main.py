"""Command-line interface for the search engine tool."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from src.crawler import DEFAULT_USER_AGENT, CrawlerError, QuoteCrawler
from src.indexer import Index, build_index, load_index, save_index
from src.robots import RobotsPolicy
from src.search import find_pages, find_phrase, format_did_you_mean, print_word

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "index.json"
TARGET_URL = "https://quotes.toscrape.com/"


def _ensure_utf8_output() -> None:
    """Reconfigure stdout/stderr to UTF-8 so Unicode chars render cleanly.

    Smoke-testing the build against quotes.toscrape.com surfaced a
    Windows-only display glitch: scraped quote text contains "smart"
    Unicode quotes (U+201C / U+201D) and the default Git-Bash stdout
    encoding (cp1252) renders them as the replacement glyph. The
    on-disk index is unaffected because :func:`save_index` writes with
    explicit ``encoding="utf-8"``; this function only fixes the live
    terminal output.

    Streams that already use UTF-8, or that don't support
    ``reconfigure`` (older Python or replaced streams), are left
    untouched. Failures are swallowed so the CLI never blocks on a
    cosmetic concern.
    """
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, "reconfigure"):
            continue
        if (stream.encoding or "").lower() == "utf-8":
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # The stream may have been replaced or detached; degrade
            # silently rather than block the CLI on cosmetics.
            pass


def run_shell() -> None:
    """Run the interactive command shell."""
    _ensure_utf8_output()
    index: Index = Index()

    print("Search Engine Tool. Type 'help' for commands or 'exit' to quit.")
    while True:
        try:
            raw_command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw_command:
            continue

        try:
            index = handle_command(raw_command, index)
        except (CrawlerError, FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}")
        except SystemExit:
            break


def handle_command(raw_command: str, index: Index) -> Index:
    """Handle one command and return the current index."""
    parts = shlex.split(raw_command)
    command = parts[0].lower()
    args = parts[1:]

    if command in {"exit", "quit"}:
        raise SystemExit
    if command == "help":
        print_help()
        return index
    if command == "build":
        print("Fetching robots.txt...")
        robots_policy = RobotsPolicy.from_url(TARGET_URL, DEFAULT_USER_AGENT)
        print("Starting crawl. This will take about one minute because of the 6-second politeness delay.")
        crawler = QuoteCrawler(
            start_url=TARGET_URL,
            robots_policy=robots_policy,
            progress_callback=lambda message: print(message, flush=True),
        )
        pages = crawler.crawl()
        print("Building inverted index...")
        index = build_index(pages)
        save_index(index, DEFAULT_INDEX_PATH)
        print(f"Built index for {len(pages)} pages and saved it to {DEFAULT_INDEX_PATH}.")
        return index
    if command == "load":
        index = load_index(DEFAULT_INDEX_PATH)
        print(f"Loaded index from {DEFAULT_INDEX_PATH}.")
        return index
    if command == "print":
        if not args:
            raise ValueError("Usage: print <word>")
        print(json.dumps(print_word(index, args[0]), indent=2, sort_keys=True))
        return index
    if command == "find":
        if not args:
            raise ValueError("Usage: find <word or phrase>")
        # A single shlex-arg containing a space comes from a quoted
        # input like `find "good friends"` — route to strict phrase
        # matching. Every other shape (one bareword, multiple words)
        # stays on the conjunctive AND path the brief specifies.
        if len(args) == 1 and " " in args[0]:
            query_text = args[0]
            results = find_phrase(index, query_text)
        else:
            query_text = " ".join(args)
            results = find_pages(index, query_text)
        if results:
            for url in results:
                print(url)
        else:
            print("No matching pages found.")
            # Offer a spelling-correction hint only when the query
            # contains at least one token the index does not know
            # AND a near-neighbour exists. Both checks live inside
            # format_did_you_mean; None means "nothing useful to
            # say, stay silent".
            hint = format_did_you_mean(index, query_text)
            if hint is not None:
                print(hint)
        return index

    raise ValueError(f"Unknown command: {command}")


def print_help() -> None:
    print("Commands:")
    print("  build              Crawl the website, build the index, and save it")
    print("  load               Load the saved index")
    print("  print <word>       Print the inverted index for a word")
    print("  find <query>       Find pages containing all query words")
    print("  exit               Quit")


if __name__ == "__main__":
    run_shell()
