# Video Script — COMP3011 CW2 Search Engine Tool (5 minutes)

The five-minute video demonstration script, organised by section. Each
row gives the timestamp, the on-screen action, and the narration to
deliver. Read row-by-row to time yourself against the budget.

The companion slide deck used for the title card, section dividers, and
the GenAI bullets is at
[`docs/video_template.pptx`](docs/video_template.pptx).

---

## Timing budget

| Section | Time | Content |
|---|---|---|
| Live Demonstration | 2:00 | Four required commands + advanced query forms + edge cases |
| Code Walkthrough & Design | 1:30 | Index dataclass, ranking, retrieval algorithms, BK-tree |
| Testing | 0:30 | 370 tests + four green CI gates |
| Version Control | 0:30 | Twenty-five release tags + feature branches + Conventional Commits |
| GenAI Critical Evaluation | 0:30 | Three concrete examples + one reflection |
| **Total** | **5:00** | |

---

## 1. Live Demonstration (0:00 – 2:00)

| Time | Screen | Say |
|---|---|---|
| **0:00** | Title slide | "Hi, this is my COMP3011 Coursework 2 submission — a search engine tool for `quotes.toscrape.com`." |
| **0:10** | Terminal at repo root | "Let me launch the CLI." → **type:** `python -m src.main` |
| **0:15** | `>` prompt + shell banner | "The brief specifies four commands: `build`, `load`, `print`, and `find`." |
| **0:20** | **Type** `build`, let the first crawl lines print, then cut in post to the `Built index for ... pages and saved it to data/index.json.` line | "`build` crawls about 200 pages — roughly 22 minutes with the six-second politeness window. I'll skip ahead to the completed state, then run `load` to bring the saved index into memory." |
| **0:32** | **Type** `load` → "Loaded index from data/index.json." | "Index loaded — version 5 schema, the latest after seven releases." |
| **0:40** | **Type** `print nonsense` → JSON output | "`print` returns the inverted-index entry for one word — a posting list keyed by URL with frequency and token positions. This is the Lecture 12 'index structure and terminology' layout, plus a per-field statistics map for Lecture 12's 'fields and extents'." |
| **1:00** | **Type** `find good friends` → URL list with `[Good] [friends]…` snippets | "Multi-word queries use conjunctive AND mode — every word must appear. That's the brief's exact example. Each result line is followed by a 60-to-80 character snippet that highlights the matching tokens in square brackets — Manning textbook chapter 8's static snippet formulation." |
| **1:20** | **Type** `find "good friends"` → shorter list with `[good friends]` as one bracketed unit | "Quoted queries trigger strict phrase matching — adjacent and in order — using the position-offset intersection trick. The snippet now brackets the whole phrase as one unit, not each token independently." |
| **1:50** | **Type** `find indiference` (typo) → "No matching pages found." then "Did you mean: indifference?" | "Zero results with an unknown token activates the 'Did you mean' path — Levenshtein distance with BK-tree acceleration on large vocabularies. I'll dig into BK-tree in the code walkthrough." |
| **2:00** | **Type** `exit` | "That's the brief commands plus advanced query processing. To the code." |

---

## 2. Code Walkthrough & Design (2:00 – 3:30)

| Time | Screen | Say |
|---|---|---|
| **2:00** | `src/indexer.py`, cursor at the `Index` dataclass and `Posting` TypedDict | "This is the `Index` dataclass and the `Posting` TypedDict that types every posting. `documents`, `postings`, `doc_lengths`, `documents_text`, and `tokenizer_config` — five fields the v1.7.0 refactor pinned with static types, so `mypy` catches an entire class of bug before the test suite runs." |
| **2:15** | `src/ranker.py`, cursor at the `Ranker` protocol | "`Ranker` is a PEP 544 protocol — structural subtyping. Two implementations: `TFIDFRanker`, the textbook vector-space baseline, and `BM25Ranker`, Croft chapter 5's Okapi formula with Robertson IDF and length normalisation." |
| **2:30** | `src/crawler.py`, the politeness floor logic | "Politeness uses `max` of six seconds and the robots crawl delay so we never violate either constraint, and the Session-with-Retry adapter handles transient five-X-X errors without aborting a 22-minute crawl." |
| **2:40** | `src/retrieval.py`, `conjunctive_match_with_skip` | "Lecture 13's skip-pointer optimisation: lagging pointers advance in sqrt-of-remaining-length jumps before a linear final-bucket scan. I kept the simple algorithm as a reference implementation and pinned their equivalence with a property test." |
| **2:55** | `phrase_match` in the same file | "Phrase queries use position-offset intersection — for each token, subtract its query offset from its positions; intersect the normalised sets; any shared value is a phrase start." |
| **3:05** | `src/bktree.py`, the `search` method | "v1.6.0 is the novel contribution. The 'Did you mean' lookup needed sub-linear vocabulary search, so I built a Burkhard-Keller metric tree. Edit distance is a metric — triangle inequality holds — which means at each node, after measuring distance to that node, I can drop any subtree whose edge-weight band is more than the threshold away." |
| **3:20** | Open [`benchmarks/results/suggest-benchmark-summary.md`](benchmarks/results/suggest-benchmark-summary.md) | "Empirical receipt: on the clustered five-thousand-word vocabulary, BK-tree is two times faster than length-pruned linear scan. The same benchmark on uniform-random vocabularies shows the algorithm's failure mode within three percent of linear — pruning needs distance clustering to bite." |

---

## 3. Testing (3:30 – 4:00)

| Time | Screen | Say |
|---|---|---|
| **3:30** | Terminal — **type** `python -W error -m unittest discover` | "Three hundred and seventy tests pass with zero warnings." |
| **3:40** | Browser tab on the GitHub Actions CI workflow run list | "And on every push, four CI gates run across Python 3.10, 3.11, and 3.12: ruff for lint, mypy for types, a pdoc smoke build that fails if any docstring stops parsing, and the full test suite under coverage with a fail-under-85% threshold — currently 94%." |
| **3:50** | `tests/` listing in PowerShell — `ls test_*.py \| Format-Table Name, Length -AutoSize` | "Four test layers: unit per module, integration against a stubbed three-page site, performance regression budgets on a 500-page synthetic corpus, and property tests that pin invariants across twenty randomised trials each." |

---

## 4. Version Control (4:00 – 4:30)

| Time | Screen | Say |
|---|---|---|
| **4:00** | Terminal — **type** `git log --graph --oneline --all -n 25` | "Twenty-five release tags from `v0.1.0` through `v1.7.0` — eighteen during the v1.0.0 base build, seven more across the post-submission roadmap." |
| **4:12** | Point at the merge-commit topology and feature branch names | "Every release got its own feature branch — those are the side forks you see here. I always used no-fast-forward merges, so the graph keeps that fork-and-merge shape instead of flattening into one line. And every commit message starts with its type — feature, refactor, docs — Conventional Commits style, scannable at a glance." |
| **4:22** | `CHANGELOG.md` open in editor | "Every release tag has a Keep-a-Changelog entry. The whole roadmap is traceable from a single file." |

---

## 5. GenAI Critical Evaluation (4:30 – 5:00)

Slide-driven section. The four bullets — **Helped / Modified / Rejected
/ Reflection** — highlight in turn as each is narrated.

| Time | Screen | Say |
|---|---|---|
| **4:30** | Slide title: "GenAI Critical Evaluation" | "I worked with Claude as a paired collaborator throughout. Three examples, one reflection." |
| **4:34** | Highlight **Helped** | "**Helped** — Claude suggested keeping the linear scan as a reference implementation, and pinning equivalence with a property test. Better than a comment claiming 'they're equivalent'." |
| **4:42** | Highlight **Modified** | "**Modified** — Claude's first Porter stemmer covered all five steps. I cut it to Step 1 — fifty lines I can defend, instead of two hundred I couldn't." |
| **4:50** | Highlight **Rejected** | "**Rejected** — Claude wanted the Hypothesis library. I stayed with stdlib random and a fixed seed — same coverage, no extra dependency." |
| **4:56** | Highlight **Reflection** | "**Reflection** — AI halved the boilerplate, but tempted shallow ownership. Property tests were my counter-discipline. Every line is defensible." |
| **5:00** | End slide | (silence) |
