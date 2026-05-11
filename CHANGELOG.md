# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/).

Each entry below corresponds to one Git tag in the repository. The
implementation steps these tags trace back to are summarised in the
[Lecture alignment](README.md#lecture-alignment) and
[Algorithms](README.md#algorithms) sections of the README.

## [1.4.0] — 2026-05-11

### Added
- `src/snippet.py` — Wagner-Fischer-free static snippet generator
  (Manning et al. Ch. 8.7). Anchors on the earliest match, expands a
  ±35-char window with a 20-char whitespace-snap slack, highlights
  matches with `[brackets]`. Phrase mode brackets the whole phrase
  as one unit.
- `Index.documents_text` field persisting raw body text per doc so
  the snippet generator can quote context without re-fetching pages.
- `find_pages_with_snippets` and `find_phrase_with_snippets` in
  `src/search.py`; the CLI `find` command surfaces `URL\n  snippet`
  per result.
- 19 tests in `tests/test_snippet.py` covering window selection,
  word boundaries, slack bounds, phrase mode, and edge cases.
- 11 tests across `tests/test_search.py` and `tests/test_main.py`
  covering the snippet wiring and CLI output format.

### Changed
- `INDEX_VERSION` bumped from 4 to 5 for the new `documents_text`
  field. **Breaking on-disk format change** — existing v4
  `data/index.json` files will be rejected by `load_index`; run
  `build` once to regenerate. The version guard surfaces a clear
  error message rather than letting a stale file silently produce
  empty snippets.

## [1.3.0] — 2026-05-11

Engineering-quality bundle: standardised project metadata, two new
CI gates, and two robustness improvements that close known failure
modes from v1.2.0.

### Added
- `pyproject.toml` (PEP 621) as the canonical project metadata,
  subsuming `.coveragerc`. Contains `[project]` block, coverage
  configuration, and pre-staged `[tool.ruff]` and `[tool.mypy]`
  configurations.
- **ruff lint as a CI gate** — fails the build on style violations
  (pyflakes, pycodestyle, import sort, bugbear). `requirements-dev.txt`
  adds `ruff>=0.4`.
- **mypy type check as a CI gate** — moderate strictness
  (`check_untyped_defs`, `warn_redundant_casts`, `warn_unused_ignores`,
  `warn_unreachable`, `no_implicit_optional`). `requirements-dev.txt`
  adds `mypy>=1.10`.
- Three atomicity tests in `tests/test_indexer.py` covering the
  happy path, mid-write failure, and mid-rename failure.
- Four crawler tests in `tests/test_crawler.py` covering session
  ownership, adapter mount points, retry configuration, and
  cross-fetch session reuse.

### Changed
- `save_index` is now atomic: writes to `<path>.tmp`, then
  `os.replace` (atomic on POSIX and Windows). A crash mid-write
  leaves the previous `index.json` untouched rather than corrupting
  it half-way.
- `QuoteCrawler` owns one `requests.Session` for its lifetime, with
  a urllib3 retry adapter mounted on both `http://` and `https://`.
  `total=3` retries, `backoff_factor=0.5`, `status_forcelist=[502, 503, 504]`,
  GET-only. Cumulative backoff stays well below the 6-second
  politeness window.
- Type narrowing in `src/crawler.py` for `BeautifulSoup.Tag.get` to
  satisfy mypy without `# type: ignore`.
- `typing.cast(int, ...)` in `src/indexer.py` and `src/ranker.py`
  where the `dict[str, object]` posting representation crosses an
  integer-only operation; refactor to a `TypedDict` deferred to v1.7.0.

### Removed
- `.coveragerc` — replaced by `[tool.coverage]` in `pyproject.toml`.

## [1.2.0] — 2026-05-11

### Added
- `src/suggest.py` — Wagner-Fischer Levenshtein distance with
  rolling two-row DP (O(min(|s1|, |s2|)) space) and a vocabulary
  candidate generator. Length-difference pruning skips terms that
  cannot be within the edit-distance threshold.
- `suggest_for_query` and `format_did_you_mean` in `src/search.py`.
- CLI `find` prints `Did you mean: <reformulated query>?` on the
  line after `No matching pages found.` when:
  1. at least one query token is missing from the index vocabulary,
     AND
  2. at least one such token has a vocabulary neighbour within
     edit distance 2.
- 22 tests in `tests/test_suggest.py`, 12 in `tests/test_search.py`,
  4 in `tests/test_main.py`, and 4 integration tests in
  `tests/test_integration.py` covering the full crawl → build →
  load → find pipeline with a typo.

### Changed
- The implementation is "plain" Levenshtein, not Damerau —
  transpositions like `freind <-> friend` cost 2 edits, not 1.
  Documented explicitly in `src/suggest.py` and pinned by a test.

## [1.1.0] — 2026-05-11

### Added
- `benchmarks/` directory with a deterministic synthetic-corpus
  generator (`benchmarks/corpus.py`) and a benchmark runner
  (`benchmarks/run_benchmarks.py`).
- Runner compares two algorithm groups against each other:
  - **Group A — ranked retrieval** (top-10): DAAT and TAAT, each
    paired with both TF-IDF and BM25.
  - **Group B — intersection only**: simple conjunctive intersection
    vs the skip-pointer variant.
  Three query shapes (single common, multi-balanced, skewed rare+common)
  with three instances each, four default sizes (250 / 500 / 1000 / 2000),
  five measured repetitions per cell plus one discarded warmup.
- Output: terminal table, JSON (full data + run metadata), CSV (flat
  schema), and Markdown (report-ready tables). All artefacts land in
  `benchmarks/results/` and are git-ignored.
- 12 tests in `tests/test_benchmarks.py` covering the synthesizer
  contract, query selection across the three shapes, and a smoke
  test that drives the full runner end-to-end with tiny inputs.
- README "Benchmarks" section documenting reproduction, methodology
  notes (warmup, IQR, time/memory separated), and the rationale for
  not running benchmarks in CI.

## [1.0.0] — 2026-05-11

Submission release. Consolidates v0.1.0 through v0.17.0; no new code,
only this changelog and a README pointer to it. The project covers
every required brief command (`build`, `load`, `print`, `find`) plus
advanced features (ranking with TF-IDF and BM25, four retrieval
algorithms, phrase queries, opt-in stopword filtering and Porter
stemming).

### Added
- `CHANGELOG.md` (this file).
- README link to the changelog from the Project structure section.

## [0.17.0] — 2026-05-11

### Added
- Publication-grade README sections: Project structure, Algorithms
  (formulas + complexity + code locations), Limitations, References
  (Croft, Manning, Porter, Robertson), Acknowledgments with explicit
  GenAI declaration, and License.

### Changed
- Refreshed existing README sections (Features, Architecture, Design
  decisions, Lecture alignment) to cover the full feature set added
  between v0.5 and v0.16.

## [0.16.0] — 2026-05-11

### Added
- `.github/workflows/ci.yml` — GitHub Actions running the test suite
  on Python 3.10, 3.11, and 3.12 with a `coverage.py --fail-under=85`
  gate (measured coverage at the time: 92.5 %).
- `.coveragerc` configuration (source = `src/`, branch coverage on).
- `requirements-dev.txt` separating dev tooling (`coverage`) from
  runtime dependencies.
- README CI status badge, coverage badge, and Python version badge.

## [0.15.0] — 2026-05-11

### Added
- `tests/test_integration.py` — full pipeline tests (crawl → build →
  save/load → search) against a stubbed three-page synthetic site.
- `tests/test_performance.py` — regression budgets for `build_index`,
  `find_pages` with TF-IDF and BM25, and save/load on a 500-page
  synthetic corpus.
- `tests/test_properties.py` — five invariants verified across 20
  randomised trials each: save/load identity, `find_pages` ⊂
  documents, `find_phrase` ⊆ `find_pages`, BM25 ≥ 0, and `tokenize`
  idempotence.

## [0.14.0] — 2026-05-11

### Added
- `conjunctive_match_with_skip` implementing Lecture 13's
  skip-pointer optimisation: lagging pointers advance in
  `sqrt(remaining)` jumps before a linear final-bucket scan.
- Property test pinning equivalence with the simple algorithm across
  20 randomised trials.

### Changed
- `conjunctive_retrieval` now uses the skip-pointer variant; the
  simple `conjunctive_match` is preserved as a reference
  implementation.

## [0.13.0] — 2026-05-11

### Added
- `src/tokenizer.py` with `TokenizerConfig`, a ~25-word English
  stopword list, and Porter Step 1 stemming (steps 1a / 1b / 1c).
- `Index.tokenizer_config` field — the build-time config is now
  persisted and propagated to search-time tokenisation
  automatically.

### Changed
- `tokenize` moved out of `src/indexer.py` into `src/tokenizer.py`;
  `indexer.py` and `search.py` import from the new location.

## [0.12.0] — 2026-05-10

### Added
- `phrase_match` and `phrase_retrieval` in `src/retrieval.py`
  implementing phrase matching via position-offset intersection.
- `find_phrase` in `src/search.py`.
- CLI routes quoted `find "..."` input to phrase mode; unquoted
  input stays on the conjunctive AND path the brief specifies.

## [0.11.0] — 2026-05-10

### Added
- `conjunctive_match` — Lecture 13's simple sorted-list intersection
  algorithm generalised to N lists — and `conjunctive_retrieval` in
  `src/retrieval.py`.

### Changed
- `find_pages` delegates to `conjunctive_retrieval` instead of
  Python's `set.intersection`.

## [0.10.0] — 2026-05-10

### Added
- `term_at_a_time` retrieval algorithm in `src/retrieval.py`.
- Equivalence tests pinning DAAT and TAAT to produce identical
  results for additive rankers (TF-IDF and BM25).

## [0.9.0] — 2026-05-10

### Added
- `src/retrieval.py` module.
- `document_at_a_time` with a bounded `(score, -doc_id)` min-heap;
  the `-doc_id` negation preserves the doc_id-ascending tiebreak
  under heap eviction.

## [0.8.0] — 2026-05-09

### Added
- `BM25Ranker` in `src/ranker.py` (Croft, Metzler & Strohman, Ch. 5):
  Robertson IDF with smoothing, document length normalisation,
  configurable `k1` and `b` parameters.
- `Index.doc_lengths` field tracking body token counts per document
  for BM25's length normalisation term.
- Tests covering TF saturation, length penalisation, Robertson IDF
  non-negativity, and the textbook formula's exact numeric value.

## [0.7.0] — 2026-05-08

### Added
- `src/ranker.py` with the `Ranker` protocol (PEP 544 structural
  subtyping) and `TFIDFRanker` implementing `tf · log(N / df)`.

### Changed
- `find_pages` accepts an optional `ranker` parameter (defaults to
  TF-IDF) and returns URLs ordered by relevance instead of
  alphabetically.

## [0.6.0] — 2026-05-08

### Added
- Per-field statistics on each posting (`posting["fields"]`) for
  Lecture 12's *Fields and Extents* concept; populated for
  `title`, `quote_text`, `author`, and `tag` fields. Sparse
  representation — zero-frequency fields are simply absent.

## [0.5.0] — 2026-05-08

### Changed
- Inverted index moved from URL-keyed postings to integer `doc_id`
  keys with a separate `Index.documents` map (Lecture 12 layout).
- Index wrapped in a versioned `Index` dataclass with
  `INDEX_VERSION`; `load_index` rejects files written under a
  different schema version with a clear "rebuild" error.

## [0.4.0] — 2026-05-07

### Added
- `src/parser.py` module hosting `parse_html_to_text` and
  `parse_html_to_fields`.
- `ParsedFields` dataclass (`title` / `quote_texts` / `authors` /
  `tags` / `body`) attached to `CrawledPage.fields`.

## [0.3.0] — 2026-05-07

### Changed
- `_parse_page` now extracts every visible body word (not just
  `.quote .text` content), satisfying the brief's *"all word
  occurrences in the pages of the website"* requirement.

## [0.2.0] — 2026-05-07

### Added
- `src/robots.py` with `RobotsPolicy` wrapping
  `urllib.robotparser.RobotFileParser`.
- Crawler honours `robots.txt` `Allow` / `Disallow` rules and
  `Crawl-delay` (taken as the maximum with the brief's 6-second
  floor).
- `main.py` fetches `/robots.txt` at the start of `build`; failures
  fall back to a permissive policy per the spec.

## [0.1.0] — 2026-05-07

### Added
- Frontier-based BFS crawler in `src/crawler.py` (replacing the
  original linear next-link walker).
- `User-Agent` HTTP header identifying the crawler with a project
  URL.
- `max_depth` parameter defending against fictitious-resource link
  traps (Lecture 9).

### Pre-history

Commits before v0.1.0 contain the initial coursework scaffold: CLI
shell with the four required `build` / `load` / `print` / `find`
commands, a single-file JSON-persisted inverted index, and the first
round of unit tests covering the indexer and search modules.

[1.4.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v1.4.0
[1.3.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v1.3.0
[1.2.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v1.2.0
[1.1.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v1.1.0
[1.0.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v1.0.0
[0.17.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.17.0
[0.16.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.16.0
[0.15.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.15.0
[0.14.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.14.0
[0.13.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.13.0
[0.12.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.12.0
[0.11.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.11.0
[0.10.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.10.0
[0.9.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.9.0
[0.8.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.8.0
[0.7.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.7.0
[0.6.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.6.0
[0.5.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.5.0
[0.4.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.4.0
[0.3.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.3.0
[0.2.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.2.0
[0.1.0]: https://github.com/SHIRUIZHAOIILLiil/search-engine-tool/releases/tag/v0.1.0
