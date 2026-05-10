# Search Engine Tool

[![CI](https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/actions/workflows/ci.yml)
![Coverage](https://img.shields.io/badge/coverage-92.5%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

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
- **Field-structured parser** — title, quote text, author, tags, and full body are extracted into a `ParsedFields` dataclass so the ranker can weight them differently.
- **Versioned inverted index** with integer `doc_id` keys, a separate URL map, and `doc_lengths` for length-normalised ranking (Lecture 12 layout).
- **TF-IDF and BM25 ranking** via a pluggable `Ranker` protocol — TF-IDF is the textbook vector-space baseline; BM25 (Croft, Ch. 5) is the industry-standard length-normalised ranker with `k1` / `b` tunables.
- **Four retrieval algorithms** from Lecture 13: document-at-a-time (DAAT), term-at-a-time (TAAT), conjunctive intersection (simple), and the skip-pointer optimised variant — DAAT and TAAT are pinned equivalent under additive rankers; the two conjunctive variants are pinned equivalent across 20 randomised trials.
- **Phrase queries** via the position-offset intersection trick — `find "good friends"` requires the tokens to appear adjacent and in order.
- **Opt-in text normalisation** — `TokenizerConfig` enables a ~25-word English stopword filter and Porter Step 1 stemming; default is off to preserve brief-compliant semantics.
- **Schema version guard** — `load` refuses to read indexes written by an incompatible version.
- **UTF-8 CLI output** — `run_shell` reconfigures stdout so smart quotes and other Unicode characters in scraped quotes render correctly on Windows terminals.
- **207 tests at 92.5 % coverage** spanning unit, integration, performance, and property layers, run on Python 3.10 / 3.11 / 3.12 in CI.

---

## Architecture

| Module | Responsibility |
|---|---|
| [`src/crawler.py`](src/crawler.py) | Frontier-based BFS, HTTP fetch, politeness window, robots gating, depth limit |
| [`src/parser.py`](src/parser.py) | HTML → visible body + structured `ParsedFields` (title / quote / author / tag) |
| [`src/robots.py`](src/robots.py) | `robots.txt` parsing and per-URL policy questions |
| [`src/tokenizer.py`](src/tokenizer.py) | Regex tokenisation + opt-in stopword filter + Porter Step 1 stemming |
| [`src/indexer.py`](src/indexer.py) | Inverted index construction, doc-id assignment, doc-length tracking, JSON persistence |
| [`src/ranker.py`](src/ranker.py) | Pluggable `Ranker` protocol with `TFIDFRanker` and `BM25Ranker` implementations |
| [`src/retrieval.py`](src/retrieval.py) | DAAT, TAAT, conjunctive (simple + skip-pointer), and phrase retrieval algorithms |
| [`src/search.py`](src/search.py) | `print_word`, `find_pages`, `find_phrase` user-facing search API |
| [`src/main.py`](src/main.py) | CLI shell — wires everything together, routes quoted input to phrase mode |

**Data flow:**

```
quotes.toscrape.com
        │
        ▼
   QuoteCrawler ──▶ CrawledPage(url, text, fields)
                            │
                            ▼  (tokenizer.py: regex / stopwords / stemming)
                     build_index(pages, config?)
                            │
                            ▼
            Index(documents, postings, doc_lengths, tokenizer_config)
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
        print_word         find_pages  /  find_phrase
                                          │
                                          ▼  (retrieval.py:
                                          │   conjunctive_retrieval /
                                          │   phrase_retrieval)
                                          ▼
                                ranker.py: TFIDFRanker / BM25Ranker
                                          │
                                          ▼
                              CLI output (URLs ordered by score)
```

---

## Setup

```bash
python -m pip install -r requirements.txt
```

Runtime dependencies declared in [`requirements.txt`](requirements.txt):

- `requests` — HTTP client
- `beautifulsoup4` — HTML parser

To run the test suite with coverage, install the development extras instead:

```bash
python -m pip install -r requirements-dev.txt
```

[`requirements-dev.txt`](requirements-dev.txt) pulls in the runtime requirements plus:

- `coverage` — line + branch coverage measurement (used by the CI gate)

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
| `find <query>` | List pages containing every word in the query, ranked by TF-IDF relevance (conjunctive AND mode) |
| `find "<phrase>"` | Quoted form: list pages containing the query as a consecutive phrase (strict adjacency) |
| `help` | Show the command list |
| `exit` / `quit` | Leave the shell |

**Example session** — the first four lines are the brief's canonical examples; the last line exercises the phrase mode added in this implementation:

```text
> build
> load
> print nonsense
> find indifference
> find good friends
> find "good friends"
```

---

## Index file format

After `build`, `data/index.json` looks like:

```json
{
  "version": 4,
  "documents": {
    "0": "https://quotes.toscrape.com/",
    "1": "https://quotes.toscrape.com/page/2/"
  },
  "doc_lengths": {
    "0": 84,
    "1": 79
  },
  "postings": {
    "good": {
      "0": {
        "frequency": 2,
        "positions": [3, 17],
        "fields": {
          "quote_text": {"frequency": 1, "positions": [0]}
        }
      },
      "1": {"frequency": 1, "positions": [4], "fields": {}}
    }
  },
  "tokenizer_config": {
    "apply_stopword_filter": false,
    "apply_stemming": false
  }
}
```

- **`version`** — schema sentinel (currently 4). `load` rejects files written under a different version and tells the user to rebuild.
- **`documents`** — integer `doc_id` → URL. JSON forces string keys; the loader converts them back to `int`.
- **`doc_lengths`** — `doc_id` → body token count, used by BM25's length-normalisation term.
- **`postings`** — term → `doc_id` → posting. Each posting has body-level `frequency` / `positions` plus a sparse per-field breakdown (`title`, `quote_text`, `author`, `tag`) for future BM25F-style ranking.
- **`tokenizer_config`** — records whether the index was built with stopword filtering or stemming so the search layer can tokenise queries the same way.

---

## Design decisions

| Choice | Why |
|---|---|
| Frontier-based BFS instead of linear next-link walking | Lecture 9: "Web crawling is usually done using a breadth-first traversal algorithm." Catches `/author/<slug>/` and `/tag/<name>/` pages alongside the paginated quote listing. |
| Integer `doc_id` keys with a separate URL map | Lecture 12: "each page is given a unique number to make it more efficient for storing document pointers." Compact postings, faster set operations, headroom for binary compression. |
| Per-field parser output (`ParsedFields`) | Lecture 11: "The main heading… is more important than the body." Quote text, author, tags, title, and body are kept separate so a BM25F-style ranker can apply per-field weights. |
| Doc lengths tracked at build time | BM25's length-normalisation term needs `dl(d)` and `avgdl` at query time. Recording lengths once during build avoids re-scanning postings later. |
| Pluggable `Ranker` protocol via PEP 544 structural subtyping | `TFIDFRanker` and `BM25Ranker` satisfy the protocol without inheritance. Adding a new ranker is one class; `find_pages` and `find_phrase` need no changes. |
| Default ranker is TF-IDF, not BM25 | TF-IDF maps directly to Lecture 12's general scoring function `R(Q,D) = Σ g_i(Q) f_i(D)`, making it the cleanest pedagogical baseline. BM25 is available via `ranker=BM25Ranker()` for production-grade retrieval. |
| Both simple and skip-pointer conjunctive intersection in the codebase | `conjunctive_match` is the Lecture 13 simple algorithm preserved as a reference implementation; `conjunctive_match_with_skip` is the production path. A property test pins their equivalence over 20 random trials so they can never silently diverge. |
| Stopwords and stemming opt-in (default `TokenizerConfig()` is off) | Lecture 11 warns aggressive stopword removal breaks queries like *"to be or not to be"*. Default-off preserves the brief's case-insensitive bag-of-words contract; the user opts in by passing a `TokenizerConfig`. |
| `tokenizer_config` stored on the index | Build-time and search-time tokenisation must agree. Storing the config on the `Index` means callers never have to remember whether stemming was enabled. |
| `find "good friends"` vs `find good friends` (phrase vs conjunctive) | One `find` command, two modes disambiguated by `shlex` quote handling. Brief's unquoted form stays AND mode; quoted form enables strict phrase matching. |
| `robots.txt` parsing with permissive fallback | Per spec, an unreachable `robots.txt` is equivalent to "no restrictions". Silently degrading avoids hard-failing the build for transient network issues. |
| `User-Agent` header advertising the project URL | Lecture 9: real crawlers identify themselves so server admins can contact the operator. The `+url` syntax matches the convention used by Googlebot et al. |
| Schema version on disk | Lets the loader reject incompatible index files with a clear "rebuild" message instead of producing wrong search results. |
| Permissive default `RobotsPolicy` in unit tests | Keeps the test suite offline; production wiring in `main.py` calls `RobotsPolicy.from_url(...)` for the real fetch. |

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
| Stopword filter (opt-in) | L11 *Function Words* / *What to do with Stopwords* |
| Porter Step 1 stemming (opt-in) | L11 *Stemming* / *Stemmer Types* |
| Inverted list / posting / term vocabulary | L12 *Index structure and terminology* |
| Frequency stored in postings | L12 *Storing Word Counts* |
| Positions stored in postings | L12 *Positions* |
| Integer `doc_id` with separate URL map | L12 *Index structure and terminology* |
| Per-field statistics (fields / extents) | L12 *Fields and Extents* |
| Ranking function `R(Q,D) = Σ g_i(Q) f_i(D)` | L12 *The Ranking Function Revisited* |
| TF-IDF as `tf · log(N/df)` | L12 ranking function instantiation |
| BM25 with Robertson IDF and length normalisation | Croft et al., *Search Engines: Information Retrieval in Practice*, Ch. 5 (cited as further reading at the end of L13) |
| Document-at-a-time retrieval with bounded priority queue | L13 *Document-at-a-time Pseudocode* / *Algorithm Features* |
| Term-at-a-time retrieval with accumulator hashtable | L13 *Term-at-a-time retrieval algorithm* |
| Conjunctive AND processing via sorted-list intersection | L13 *Conjunctive Processing* / *Processing Conjunctive Queries, Simple Algorithm* |
| List-skipping optimisation for skewed query terms | L13 *List Skipping* / *Skip Pointers* / *List Skipping Optimization* |
| Phrase queries via position-offset intersection | Manning, Raghavan & Schütze, *Introduction to Information Retrieval*, §2.4 (positional indexes) |

---

## Testing

```bash
python -m unittest discover
```

The test suite currently runs **207 tests** with no warnings and reaches **92.5 % line + branch coverage** of `src/`.

| File | Layer | Coverage |
|---|---|---|
| [`tests/test_crawler.py`](tests/test_crawler.py) | Unit | Fetch, BFS frontier, link extraction, politeness, robots integration |
| [`tests/test_parser.py`](tests/test_parser.py) | Unit | Visible-text extraction, field extraction, `<script>`/`<style>` filtering |
| [`tests/test_robots.py`](tests/test_robots.py) | Unit | `Disallow` matching, `Crawl-delay`, factories (`from_text` / `from_url`), fetch fallback |
| [`tests/test_tokenizer.py`](tests/test_tokenizer.py) | Unit | Default tokeniser, stopword filter, Porter Step 1 stemming |
| [`tests/test_indexer.py`](tests/test_indexer.py) | Unit | Build, doc-id assignment, fields/extents, doc-length tracking, save/load |
| [`tests/test_ranker.py`](tests/test_ranker.py) | Unit | TF-IDF and BM25 formulas, edge cases, Ranker protocol |
| [`tests/test_retrieval.py`](tests/test_retrieval.py) | Unit | DAAT / TAAT / conjunctive / skip-pointer / phrase algorithms |
| [`tests/test_search.py`](tests/test_search.py) | Unit | `print_word`, `find_pages`, `find_phrase` user-facing behaviour |
| [`tests/test_main.py`](tests/test_main.py) | Unit | CLI command handler, robots wiring, UTF-8 stdout |
| [`tests/test_integration.py`](tests/test_integration.py) | Integration | Full pipeline: stub HTTP → crawl → build → save/load → find / phrase |
| [`tests/test_performance.py`](tests/test_performance.py) | Performance | Regression budgets on 500-page synthetic corpus |
| [`tests/test_properties.py`](tests/test_properties.py) | Property | Invariants over 20-trial randomised inputs (save/load identity, phrase ⊆ AND, BM25 ≥ 0, …) |

### Continuous integration

Every push to `main` and every pull request triggers
[`.github/workflows/ci.yml`](.github/workflows/ci.yml). The workflow:

* runs the full test suite under [`coverage.py`](https://coverage.readthedocs.io/) on a Python 3.10 / 3.11 / 3.12 matrix,
* prints a per-module coverage report with missing-line numbers, and
* **fails the build if total coverage drops below 85 %** (current: 92.5 %).

A green CI badge above means the latest `main` commit passes all 207 tests on all three supported Python versions.
