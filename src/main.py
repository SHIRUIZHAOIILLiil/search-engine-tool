"""Command-line interface for the search engine tool."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from src.crawler import DEFAULT_USER_AGENT, CrawlerError, QuoteCrawler
from src.indexer import Index, build_index, load_index, save_index
from src.robots import RobotsPolicy
from src.search import find_pages, print_word

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "index.json"
TARGET_URL = "https://quotes.toscrape.com/"


def run_shell() -> None:
    """Run the interactive command shell."""
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
        results = find_pages(index, " ".join(args))
        if results:
            for url in results:
                print(url)
        else:
            print("No matching pages found.")
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
