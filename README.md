# Search Engine Tool

Coursework 2 project for **COMP3011 Web Services and Web Data**.

The tool crawls [`https://quotes.toscrape.com/`](https://quotes.toscrape.com/), builds an inverted index of every word it finds, and exposes a small command-line shell with four commands (`build`, `load`, `print`, `find`) for searching the site offline.

---

## Features

- **BFS crawl** over the same-host link graph (Lecture 9) — seeds → frontier queue → fetch → parse → enqueue links → repeat.
- **robots.txt aware** — parses `User-agent` / `Allow` / `Disallow` / `Crawl-delay`; falls back to a permissive policy if the file is unreachable (per the spec).
- **Politeness floor of 6 s** between requests, raised automatically if `Crawl-delay` is larger.
- **`User-Agent` header** identifies the crawler with a project URL so server admins can reach the operator.
- **Depth limit** defends against fictitious-resource link traps.
- **Two-pass HTML parsing** (BeautifulSoup → text) — `<script>` and `<style>` are dropped before extraction.
- **Field-structured parser** — quote text, author, tags, page title, and full body are stored separately so future rankers can weight them differently.
- **Versioned inverted index** with integer `doc_id` keys and a separate URL map (Lecture 12 layout).
- **Schema version guard** — `load` refuses to read indexes written by an incompatible version.
- **88 unit tests** covering crawler, parser, robots policy, indexer, search, and CLI wiring.

---

## Architecture

| Module | Responsibility |
|---|---|
| [`src/crawler.py`](src/crawler.py) | Frontier-based BFS, HTTP fetch, politeness window, robots gating |
| [`src/parser.py`](src/parser.py) | HTML → visible text + structured `ParsedFields` extraction |
| [`src/robots.py`](src/robots.py) | `robots.txt` parsing and per-URL policy questions |
| [`src/indexer.py`](src/indexer.py) | Tokenisation, inverted index construction, JSON persistence |
| [`src/search.py`](src/search.py) | `print` and `find` over the index |
| [`src/main.py`](src/main.py) | CLI shell wiring everything together |

**Data flow:**

```
quotes.toscrape.com
        │
        ▼
   QuoteCrawler ──▶ CrawledPage(url, text, fields)
                            │
                            ▼
                     build_index(pages) ──▶ Index(version, documents, postings)
                                                       │
                                                       ▼
                                            print_word / find_pages
                                                       │
                                                       ▼
                                            CLI output (URLs)
```

---

## Setup

```bash
python -m pip install -r requirements.txt
```

Dependencies declared in [`requirements.txt`](requirements.txt):

- `requests` — HTTP client
- `beautifulsoup4` — HTML parser

Tested with Python 3.10+.

---

## Usage

```bash
python -m src.main
```

At the `>` prompt:

| Command | Effect |
|---|---|
| `build` | Fetch `robots.txt`, BFS-crawl the site (~1 min), build the index, save to `data/index.json` |
| `load` | Load a previously saved index |
| `print <word>` | Print the posting list for one word |
| `find <query>` | List pages containing every word in the query |
| `help` | Show the command list |
| `exit` / `quit` | Leave the shell |

**Example session** (taken straight from the assessment brief):

```text
> build
> load
> print nonsense
> find indifference
> find good friends
```

---

## Index file format

After `build`, `data/index.json` looks like:

```json
{
  "version": 2,
  "documents": {
    "0": "https://quotes.toscrape.com/",
    "1": "https://quotes.toscrape.com/page/2/"
  },
  "postings": {
    "good": {
      "0": {"frequency": 2, "positions": [3, 17]},
      "1": {"frequency": 1, "positions": [4]}
    }
  }
}
```

- **`version`** — schema sentinel. `load` rejects files written under a different version and tells the user to rebuild.
- **`documents`** — integer `doc_id` → URL. JSON forces string keys; the loader converts them back to `int`.
- **`postings`** — term → `doc_id` → `{frequency, positions}`. Storing integer ids keeps lists compact and is ready for binary compression in a future revision.

---

## Design decisions

| Choice | Why |
|---|---|
| Frontier-based BFS instead of linear next-link walking | Lecture 9: "Web crawling is usually done using a breadth-first traversal algorithm." Catches `/author/<slug>/` and `/tag/<name>/` pages alongside the paginated quote listing. |
| Integer `doc_id` keys with a separate URL map | Lecture 12: "each page is given a unique number to make it more efficient for storing document pointers." Compact postings, faster set operations, headroom for compression. |
| Per-field parser output (`ParsedFields`) | Lecture 11: "The main heading… is more important than the body." Quote text, author, tags, title, and body are kept separate so a future ranker (BM25F-style) can apply per-field weights. |
| `robots.txt` parsing with permissive fallback | Standard polite-crawler behaviour. Per spec, an unreachable `robots.txt` is equivalent to "no restrictions" — silently degrading to permissive avoids hard-failing the build for transient network issues. |
| `User-Agent` header advertising the project URL | Lecture 9: real crawlers identify themselves so server admins can contact the operator. The `+url` syntax matches the convention used by Googlebot et al. |
| Schema version on disk | Lets the loader reject incompatible index files with a clear "rebuild" message instead of producing wrong search results. |
| Permissive default `RobotsPolicy` | Keeps unit tests offline by default; the production wiring in `main.py` swaps in `RobotsPolicy.from_url(...)` for the real fetch. |

---

## Lecture alignment

| Implementation | Lecture / slide |
|---|---|
| Seeds → frontier queue → fetch → parse-for-links loop | L9 *The Crawling Process* |
| `User-Agent` HTTP header | L9 *How do crawlers… declare themselves?* |
| Politeness window between requests | L9 *Politeness Policies* |
| `robots.txt` directives (`Allow` / `Disallow` / `Crawl-delay`) | L9 *The robots.txt file* |
| Depth limit against fictitious-resource traps | L9 *Fictitious Resources* |
| Two-pass tokenisation (markup → text) | L11 *Two-pass Tokenization* |
| Per-field document structure | L11 *Document Structure and Markup* |
| Inverted list / posting / term vocabulary | L12 *Index structure and terminology* |
| Frequency stored in postings | L12 *Storing Word Counts* |
| Positions stored in postings | L12 *Positions* |
| Integer `doc_id` with separate URL map | L12 *Index structure and terminology* |
| Versioned schema, fields/extents (in progress) | L12 *Fields and Extents* |

---

## Testing

```bash
python -m unittest discover
```

The test suite currently runs **88 unit tests** with no warnings.

| File | Coverage |
|---|---|
| [`tests/test_crawler.py`](tests/test_crawler.py) | Fetch, BFS frontier, link extraction, politeness, robots integration |
| [`tests/test_parser.py`](tests/test_parser.py) | Visible-text extraction, field extraction, `<script>`/`<style>` filtering |
| [`tests/test_robots.py`](tests/test_robots.py) | `Disallow` matching, `Crawl-delay`, factories (`from_text` / `from_url`), fetch fallback |
| [`tests/test_indexer.py`](tests/test_indexer.py) | Tokenisation, build, doc-id assignment, save/load round-trip, schema-version validation |
| [`tests/test_search.py`](tests/test_search.py) | `print` and `find` behaviours including empty / punctuation / repeated / missing query terms |
| [`tests/test_main.py`](tests/test_main.py) | CLI command handler, robots wiring |

Integration, performance, and property-based tests are planned for a later commit and will live alongside the existing unit suite.
