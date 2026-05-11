# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/).

Each entry below corresponds to one Git tag in the repository. The
implementation steps these tags trace back to are summarised in the
[Lecture alignment](README.md#lecture-alignment) and
[Algorithms](README.md#algorithms) sections of the README.

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
