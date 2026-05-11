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
- **Query suggestions ("Did you mean...?")** — when `find` returns zero results and at least one query token is missing from the index vocabulary, the CLI offers a reformulated query using Levenshtein-distance lookups (Manning et al., Ch. 3).
- **Highlighted snippets** — each `find` result now prints a 60-80 character body excerpt with the matching tokens wrapped in `[brackets]` (Manning et al., Ch. 8.7 "Summarization and snippet generation"). Phrase queries highlight the whole phrase as one unit.
- **Faceted search** — `find author=einstein wisdom` filters by structural field on top of the conjunctive AND match. Same field with multiple values is OR (`tag=science tag=physics`); across fields is AND. Builds on Lecture 12's "Fields and Extents" representation already present in every posting.
- **Atomic index persistence** — `save_index` writes via a sibling `.tmp` file and `os.replace`, so a crash during `build` leaves the previous good `index.json` untouched.
- **Connection-pooled crawler** — one `requests.Session` per crawler with a urllib3 retry adapter (`total=3`, exponential backoff, `502/503/504` only) keeps a single transient network blip from aborting a whole crawl.
- **Schema version guard** — `load` refuses to read indexes written by an incompatible version.
- **UTF-8 CLI output** — `run_shell` reconfigures stdout so smart quotes and other Unicode characters in scraped quotes render correctly on Windows terminals.
- **Three CI gates** — ruff lint, mypy type check, and the test suite all run on every push/PR; coverage must stay above 85 %.
- **338 tests at 93 %+ coverage** spanning unit, integration, performance, and property layers, run on Python 3.10 / 3.11 / 3.12 in CI.

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

## Project structure

```
search-engine-tool/
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions: tests + coverage on push/PR
├── data/
│   └── index.json             # produced by `build` (gitignored)
├── src/
│   ├── crawler.py             # BFS crawler + politeness + robots gating
│   ├── parser.py              # HTML → ParsedFields
│   ├── robots.py              # robots.txt parsing
│   ├── tokenizer.py           # tokenisation + stopwords + Porter stemming
│   ├── indexer.py             # build_index / save_index / load_index
│   ├── ranker.py              # Ranker protocol + TFIDFRanker + BM25Ranker
│   ├── retrieval.py           # DAAT / TAAT / conjunctive / phrase
│   ├── search.py              # print_word / find_pages / find_phrase
│   └── main.py                # CLI entry point
├── tests/
│   ├── test_crawler.py
│   ├── test_parser.py
│   ├── test_robots.py
│   ├── test_tokenizer.py
│   ├── test_indexer.py
│   ├── test_ranker.py
│   ├── test_retrieval.py
│   ├── test_search.py
│   ├── test_main.py
│   ├── test_integration.py    # full-pipeline tests
│   ├── test_performance.py    # regression budgets
│   └── test_properties.py     # randomised invariant tests
├── .coveragerc                # coverage.py configuration
├── .gitignore
├── CHANGELOG.md               # release history (Keep a Changelog format)
├── LICENSE                    # MIT
├── README.md                  # this file
├── requirements.txt           # runtime: requests + beautifulsoup4
└── requirements-dev.txt       # runtime + coverage
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

**Example session** — the first four lines are the brief's canonical examples; subsequent lines exercise the phrase mode and the spelling-correction hint added in this implementation:

```text
> build
> load
> print nonsense
> find indifference
https://quotes.toscrape.com/page/12/
  ... it is our [indifference] that hurts ...

> find good friends
https://quotes.toscrape.com/page/1/
  ... [Good] [friends] are like stars - you don't always see them ...

> find "good friends"
https://quotes.toscrape.com/page/1/
  ... we are all [good friends] here, sharing the journey ...

> find author=einstein wisdom
https://quotes.toscrape.com/page/3/
  ... the only source of [wisdom] is experience ...

> find tag=science tag=physics
https://quotes.toscrape.com/page/4/
  imagination is more important than knowledge ...
https://quotes.toscrape.com/page/9/
  the important thing is not to stop questioning ...

> find indiference
No matching pages found.
Did you mean: indifference?
```

Each `find` result is followed by a context snippet on the next line,
indented two spaces and with the matched terms wrapped in
`[brackets]`. Quoted phrase queries highlight the whole phrase as one
unit; conjunctive queries bracket each token independently. Args of
the shape `field=value` (one of `author`, `tag`, `title`, `quote_text`)
become facet filters layered on top of the free-text match — facets
and phrases can be combined freely (`find "good friends" author=wilde`).

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

## Algorithms

Formulas, complexity, and code location for each non-trivial algorithm.
Implementations live in [`src/ranker.py`](src/ranker.py) and
[`src/retrieval.py`](src/retrieval.py).

### TF-IDF (vector-space scoring)

```
score(t, d) = tf(t, d) · log(N / df(t))
score(q, d) = Σ_{t ∈ q} score(t, d)
```

where `tf(t, d)` is the raw frequency stored in the posting, `df(t)` is
the number of documents containing `t`, and `N` is the total document
count. **Complexity** *O(|q|)* per (query, doc). The default ranker used
by `find_pages` when no `Ranker` is supplied. Source:
`src/ranker.py::TFIDFRanker`.

### BM25 (Okapi)

The industry-standard ranker; Lucene and Elasticsearch use it by default.

```
BM25(t, d) = idf(t) · (tf · (k1 + 1)) / (tf + k1 · (1 − b + b · dl/avgdl))
idf(t)     = log((N − df(t) + 0.5) / (df(t) + 0.5) + 1)        ← Robertson IDF
```

Default `k1 = 1.5`, `b = 0.75` (textbook midpoint, configurable on the
constructor). BM25 improves on plain TF-IDF in three ways: TF saturation
(additional occurrences give diminishing returns), document length
normalisation (long documents are penalised), and smoothed IDF
(non-negative even when the term appears in every document). Source:
`src/ranker.py::BM25Ranker`.

### Conjunctive intersection (simple)

N-list generalisation of Lecture 13's two-list (`galago` / `animal`)
walk: keep one pointer per query token's sorted posting list, emit a
doc_id when every pointer agrees on the same value, and advance the
lagging pointers when they don't. **Complexity** linear in the sum of
posting list lengths. Source: `src/retrieval.py::conjunctive_match`.

### Skip-pointer conjunctive intersection

Same problem, optimised. Lagging pointers advance in
`sqrt(remaining_length)` jumps before falling back to a linear scan over
the final bucket — Lecture 13's "skip pointers" optimisation, in entries
rather than the slide deck's bytes. For skewed queries (one rare term,
one common term) this reduces work from *O(N)* to roughly *O(√N)* on
the long list. The two algorithms are pinned equivalent across 20
randomised property-based trials. Source:
`src/retrieval.py::conjunctive_match_with_skip`.

### Document-at-a-Time retrieval (DAAT)

Outer loop iterates candidate documents; inner loop accumulates each
doc's score across the query terms; a bounded min-heap of `(score,
−doc_id)` keeps the top *k* without holding every score in memory. The
`−doc_id` negation makes the smallest-doc_id tiebreak survive eviction
correctly when scores collide. **Memory** *O(k)*; **disk** more seeks
(jumps between posting lists per doc). Source:
`src/retrieval.py::document_at_a_time`.

### Term-at-a-Time retrieval (TAAT)

Outer loop iterates query terms; inner loop reads each posting list
start-to-finish, adding partial scores to an accumulator hashtable.
After every list is processed, the accumulators are sorted into the
final ranked list. **Memory** *O(unique candidate documents)*; **disk**
minimal seeking (sequential list reads). Source:
`src/retrieval.py::term_at_a_time`. A property test pins TAAT and DAAT
equivalent for additive rankers (TF-IDF and BM25 qualify).

### Phrase query (position-offset intersection)

For a phrase `[t_0, t_1, …, t_{n−1}]` to occur in document `d` starting
at position `p`, the index must record `t_i` at position `p + i` for
every `i`. Equivalently:

```
normalised_i = { pos − i : pos ∈ positions(t_i, d), pos ≥ i }
phrase exists ⇔ intersection(normalised_0, …, normalised_{n−1}) ≠ ∅
```

The shared value in the intersection is exactly `p`, the phrase's
starting position. A conjunctive prefilter eliminates non-candidate
documents without touching positions. Source:
`src/retrieval.py::phrase_match`.

### Spelling correction (Levenshtein edit distance)

When a `find` invocation returns zero results, the CLI inspects each
query token against the index's posting-list vocabulary. If at least
one token is unknown AND at least one near-neighbour exists within
two edits, a reformulated query is printed:

```
> find indiference
No matching pages found.
Did you mean: indifference?
```

Edit distance follows the textbook Wagner–Fischer dynamic program
(Manning, Raghavan & Schütze, *Introduction to Information
Retrieval*, Ch. 3). Substitutions, insertions and deletions each
cost 1; transpositions cost 2 (this is plain Levenshtein, not
Damerau). The implementation is space-optimised to *O(min(|s1|,
|s2|))* via a rolling two-row buffer, and prunes candidates whose
length differs from the query token by more than the distance
threshold before running the DP.

**Suppression rules** — the hint is deliberately silent when:

* every query token is already in the vocabulary (zero results are
  then an AND-filter miss, not a typo), or
* an unknown token has no candidate within the distance threshold
  (no useful correction to offer).

This avoids the "Did you mean: <synonym>?" noise that would otherwise
appear on legitimate but rare queries. Source:
[`src/suggest.py`](src/suggest.py) (distance + candidate generation),
[`src/search.py::format_did_you_mean`](src/search.py) (CLI hint
formatter).

At v1.2.0's scale (vocabulary ≲ 5 000 terms) the suggestion path
runs a linear scan over the vocabulary at query time. A BK-tree
index would cut this to *O(log N)* — that optimisation is queued for
v1.6.0 and will slot under the same public API.

### Snippet generation (Manning et al. Ch. 8.7)

For each result `find` returns, the CLI prints a ~70-character body
excerpt anchored on the earliest query-term match, with every
occurrence of any query token wrapped in `[brackets]`:

```
https://quotes.toscrape.com/page/3/
  ... we are all [good friends] here, sharing the day ...
```

The snippet generator follows the **static** snippet strategy from
Manning, Raghavan & Schutze's *Introduction to Information Retrieval*
Ch. 8.7: quote a fixed window around the first match, mark
truncation with ellipses, highlight the matched terms. The
alternative *dynamic* strategy (selecting sentences ranked by
query-term density) is out of scope here.

Implementation in [`src/snippet.py`](src/snippet.py):

1. A case-insensitive `\b<token>\b` regex finds the earliest match in
   the raw body text stored on the index (`Index.documents_text`,
   added at `INDEX_VERSION` 5). The word-boundary anchors prevent
   spurious `good`-inside-`goodness` matches.
2. The window expands ±35 characters around the anchor, with a 20-char
   slack for snapping to whitespace so the snippet does not start or
   end mid-word. Internal whitespace is collapsed to single spaces so
   multi-line bodies still produce a one-line excerpt.
3. Inside the window, every occurrence of any query token (or the
   whole phrase in phrase-mode queries) is wrapped in `[brackets]`.
   Original case is preserved (`[Good]`, not `[good]`).
4. `...` prefix/suffix is added when the window does not reach the
   body start/end, signalling truncation.

The bracket markup (rather than ANSI colour codes) is deliberate —
it asserts cleanly in tests, renders identically on every terminal,
and copies into video screen recordings without escape-code noise.

**Known limitation**: when the index was built with stemming enabled,
a query token like `run` will not surface a snippet on a document
whose body contains only `running` — the raw-text substring lookup
sees `run` as not present. Default configuration has stemming off, so
this is unobservable on the brief's primary workflow.

### Faceted search (Lecture 12 Fields & Extents)

`find` accepts `field=value` arguments that filter results by the
structural fields already populated on every posting (`title`,
`quote_text`, `author`, `tag`). The free-text portion (anything
without an `=`) follows the brief's conjunctive AND semantics
verbatim — facets are strictly additive syntax sugar, never a
replacement.

```
> find author=einstein wisdom         # Einstein quotes containing "wisdom"
> find tag=science tag=physics        # docs tagged science OR physics
> find author=wilde tag=wit           # author=wilde AND tag=wit
> find author="oscar wilde" wisdom    # multi-token value via quotes
> find "good friends" author=einstein # phrase + facet combine freely
> find tag=science                    # facet-only browse (no free text)
```

**Semantics** (settled in the v1.5.0 design):

* **Within one field, multiple values are OR.** `tag=science tag=physics`
  keeps any document whose `tag` field contains `science` OR `physics`
  — the conventional facet-UI behaviour where ticking two tags under
  one heading widens the result set.
* **Across fields, the join is AND.** `author=wilde tag=wit` requires
  both filters to match the same document.
* **Multi-token values are AND inside the value.** `author="oscar wilde"`
  requires both `oscar` AND `wilde` to appear in the same document's
  `author` field — the natural shape of multi-word names.

**Validation**: unknown fields (`author=einstein` works, `athor=einstein`
errors) and empty values (`author=`) raise immediately with a list of
known fields, so a typo produces a clear error rather than a silent
empty result.

**Implementation** ([`src/search.py::filter_by_facets`](src/search.py)):
the facet pass is a *post-filter* on conjunctive / phrase retrieval
results. Each surviving document is checked against the facets via
the per-field statistics on every posting
(`posting["fields"][field_name]["frequency"]`) — Lecture 12's
"Fields and Extents" structure paying off without needing additional
index columns. Tokenisation of facet values runs through the same
`index.tokenizer_config` that built the index so case-folding stays
consistent.

When the query has no free-text tokens (a pure facet browse like
`find tag=science`), the result list is doc_id-ordered and each
snippet falls back to a plain ~70-character head-of-body preview
without highlights.

---

## Benchmarks

The complexity claims above (TF-IDF *O(|q|)*, skip pointers *O(√N)*,
TAAT memory *O(unique candidates)*, …) are also exercised empirically
under [`benchmarks/`](benchmarks/) on synthetic corpora of varying
scale. Numbers belong in the report; this section explains how to
reproduce them and how to read the output.

### Reproducing

```powershell
# Default sweep: sizes 250 / 500 / 1000 / 2000, 5 measured reps per cell.
python -m benchmarks.run_benchmarks

# Fast development mode: sizes 50 / 100, 2 reps. ~1 second wall-clock.
python -m benchmarks.run_benchmarks --quick

# Custom sizes and rep count.
python -m benchmarks.run_benchmarks --sizes 500,5000 --reps 10
```

Results land in [`benchmarks/results/`](benchmarks/results/) as three
co-timestamped artefacts: a `.json` file (full data, machine-readable,
with run metadata), a `.csv` file (flat schema for Excel / pandas),
and a `.md` file (report-ready tables). All three are gitignored —
they are reproducible from the runner.

### Reading the output

The runner separates two **algorithm groups** whose numbers are not
comparable head-to-head:

* **Group A — ranked retrieval** (top-10): DAAT and TAAT, each paired
  with both TF-IDF and BM25. Output is a scored result list.
* **Group B — intersection only**: simple conjunctive intersection
  versus the skip-pointer variant. Output is a raw doc-id list.

Mixing the groups would mislead — Group B is always faster because it
does no scoring, regardless of the intersection algorithm's actual
quality. The lecture-13 question "does skip pointer help?" only has
meaning within Group B.

Three **query shapes** exercise the lecture-13 trade-offs:

| shape | composition | what it stresses |
|---|---|---|
| `single_common` | 1 high-frequency token | baseline (small candidate set) |
| `multi_balanced` | 2 medium-frequency tokens | worst case for TAAT's accumulator dictionary |
| `skewed_rare_common` | 1 rare + 1 common token | canonical skip-pointer win case (Lecture 13 slides 18–23) |

Three independent token instances are drawn per shape, so the table
shows within-shape variance rather than a single point estimate.

### Methodology notes

* **Warmup**: the first repetition of every cell is discarded
  (absorbs first-call costs like dict resizing).
* **Time and memory measured in separate passes**. `tracemalloc`
  adds 5–10× overhead to the code under test, so mixing it into the
  timing pass would contaminate the numbers.
* **Reported statistic**: median plus inter-quartile range across the
  measured reps. IQR is more robust to outliers than min/max, which
  follows IR-evaluation convention.
* **Reproducibility metadata** in every output: git SHA, Python
  version, platform, processor, run timestamp, full CLI parameters.

The benchmark is **not run on CI** — timing noise from shared runners
would make any threshold either too loose to catch regressions or too
strict to be stable. Performance regressions on the *correctness*
path are still caught by [`tests/test_performance.py`](tests/test_performance.py),
which uses generous fixed budgets.

See [`benchmarks/run_benchmarks.py`](benchmarks/run_benchmarks.py)
for the implementation.

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

The test suite currently runs **338 tests** with no warnings and reaches **93 %+ line + branch coverage** of `src/` (the benchmark helpers under `benchmarks/` are exercised by `tests/test_benchmarks.py` and are not counted toward `src/` coverage).

| File | Layer | Coverage |
|---|---|---|
| [`tests/test_crawler.py`](tests/test_crawler.py) | Unit | Fetch, BFS frontier, link extraction, politeness, robots integration |
| [`tests/test_parser.py`](tests/test_parser.py) | Unit | Visible-text extraction, field extraction, `<script>`/`<style>` filtering |
| [`tests/test_robots.py`](tests/test_robots.py) | Unit | `Disallow` matching, `Crawl-delay`, factories (`from_text` / `from_url`), fetch fallback |
| [`tests/test_tokenizer.py`](tests/test_tokenizer.py) | Unit | Default tokeniser, stopword filter, Porter Step 1 stemming |
| [`tests/test_indexer.py`](tests/test_indexer.py) | Unit | Build, doc-id assignment, fields/extents, doc-length tracking, save/load |
| [`tests/test_ranker.py`](tests/test_ranker.py) | Unit | TF-IDF and BM25 formulas, edge cases, Ranker protocol |
| [`tests/test_retrieval.py`](tests/test_retrieval.py) | Unit | DAAT / TAAT / conjunctive / skip-pointer / phrase algorithms |
| [`tests/test_search.py`](tests/test_search.py) | Unit | `print_word`, `find_pages`, `find_phrase`, `suggest_for_query`, `format_did_you_mean` user-facing behaviour |
| [`tests/test_suggest.py`](tests/test_suggest.py) | Unit | Wagner-Fischer Levenshtein distance and vocabulary-based candidate generation |
| [`tests/test_snippet.py`](tests/test_snippet.py) | Unit | Window selection, word-boundary snap with slack bound, highlight markup, phrase mode |
| [`tests/test_main.py`](tests/test_main.py) | Unit | CLI command handler, robots wiring, UTF-8 stdout |
| [`tests/test_integration.py`](tests/test_integration.py) | Integration | Full pipeline: stub HTTP → crawl → build → save/load → find / phrase |
| [`tests/test_performance.py`](tests/test_performance.py) | Performance | Regression budgets on 500-page synthetic corpus |
| [`tests/test_properties.py`](tests/test_properties.py) | Property | Invariants over 20-trial randomised inputs (save/load identity, phrase ⊆ AND, BM25 ≥ 0, …) |
| [`tests/test_benchmarks.py`](tests/test_benchmarks.py) | Unit / Smoke | Deterministic corpus contract; query-selection shapes; runner end-to-end with tiny inputs |

### Continuous integration

Every push to `main` and every pull request triggers
[`.github/workflows/ci.yml`](.github/workflows/ci.yml). The workflow
runs **three gates in order, fail-fast** on a Python 3.10 / 3.11 / 3.12
matrix:

1. **ruff lint** — `ruff check src/ tests/ benchmarks/` with the rule
   set in `pyproject.toml` (pyflakes, pycodestyle, import sort, bugbear).
2. **mypy type check** — moderate strictness configured in
   `pyproject.toml`; catches mismatched type annotations on every push.
3. **Test suite under coverage** — full unit / integration / property /
   performance run, with a per-module report and a **fail-under-85 %
   coverage gate** (current: 93 %+).

A green CI badge above means the latest `main` commit clears all
three gates (currently 338 tests) on all three supported Python versions.

---

## Limitations

Known limitations of the current implementation, captured here for
honesty and because they motivate the "future work" portion of the
video demonstration:

- **Phrase queries can spuriously match across structural boundaries.**
  Body positions are global offsets through the flattened body text, so
  a phrase whose first token is the last word of one structural element
  and whose second token is the first word of the next can match
  falsely. A correct fix would have the indexer carry phrase-boundary
  tokens. The limitation is documented in `phrase_match`'s docstring;
  quotes.toscrape.com rarely surfaces it in practice.
- **The crawler doesn't honour `<base href>` in HTML `<head>`.** URLs
  are resolved against the requesting URL only. The target site doesn't
  use `<base>`, so this doesn't affect this submission, but a general
  crawler would.
- **URL normalisation is minimal.** `/page/2/` and `/page/2` would be
  treated as distinct URLs. The target site is internally consistent,
  so there's no actual duplication in practice.
- **`build_index` is batch-only.** Re-running `build` rebuilds from
  scratch; there is no incremental update path.
- **`save_index` is not atomic.** A crash mid-write leaves a partial
  JSON file. The loader rejects it via the version / schema check
  rather than silently producing wrong results.
- **The Porter stemmer is Step 1 only.** Steps 2 – 5 of Porter's
  original algorithm (derivational suffixes such as `-ization`,
  `-fulness`) are omitted; Lecture 11 notes English stemming
  improvements are typically below 5 %, so Step 1 captures most of
  the value with a fraction of the code.
- **The stopword list is intentionally small (~25 words).** Larger
  lists (NLTK's 179, sklearn's 318) risk the *"to be or not to be"*
  failure mode Lecture 11 specifically warns about.

---

## References

- **Croft, W. B., Metzler, D., & Strohman, T.** (2010). *Search Engines:
  Information Retrieval in Practice*. Addison-Wesley. — Chapter 5 is the
  source for BM25, length normalisation, and the DAAT / TAAT pseudocode
  reproduced in Lecture 13; cited as further reading at the end of L13.
- **Manning, C. D., Raghavan, P., & Schütze, H.** (2008). *Introduction
  to Information Retrieval*. Cambridge University Press. — Source for
  the positional-index phrase-query technique used in `phrase_match`.
- **Porter, M. F.** (1980). *An algorithm for suffix stripping*.
  *Program* 14(3), 130 – 137. — Steps 1a, 1b, and 1c implemented in
  `src/tokenizer.py::porter_stem`.
- **Robertson, S. E., Walker, S., Jones, S., Hancock-Beaulieu, M. M.,
  & Gatford, M.** (1995). *Okapi at TREC-3*. Proceedings of the Third
  Text REtrieval Conference. — Origin of the BM25 formula and the
  Robertson IDF smoothing used by `BM25Ranker`.

---

## Acknowledgments

- **Dr Ammar Alsalka** — module lead for COMP3011 Web Services and Web
  Data. The lecture slides and assessment brief shaped the design from
  BFS crawling (Lecture 9) through skip-pointer retrieval (Lecture 13).
- **Mr Omar Choudhry** — module teaching assistant.
- [`quotes.toscrape.com`](https://quotes.toscrape.com/) — the target
  crawling site, deliberately maintained as a scrape-friendly fixture.

### Use of Generative AI

This implementation was developed with the assistance of Anthropic
Claude (via Claude Code) as a paired design and code-review collaborator
throughout the iterative development of the project.

Every line of code in this submission has been read, understood, and
deliberately retained by the author. Architectural decisions —
including the choice to keep both the simple and skip-pointer
conjunctive intersection in the codebase, the decision to default
stopword filtering and stemming OFF for brief compliance, and the
property-based testing strategy with deterministic random seeds — are
explicit trade-offs the author chose to make rather than passive
acceptance of AI output.

A detailed critical evaluation of the AI workflow — including specific
examples of where suggestions were accepted, modified, or rejected, and
the impact on learning — is presented in the accompanying 5-minute
video demonstration as required by the assessment brief.

---

## License

Released under the [MIT License](LICENSE).
