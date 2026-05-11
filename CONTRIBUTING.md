# Contributing

This guide is for anyone extending the search engine tool —
classmates, future maintainers, or future-me revisiting the project
after a year. It covers local setup, the test/lint/type-check
toolchain, commit and branching conventions, and how to land a new
feature without breaking the brief-compliance invariants.

Start with the [README](README.md) for the user-facing tour, then
[`docs/architecture.md`](docs/architecture.md) for the system view.
This file picks up where those leave off and explains *how to make
changes*.

---

## 1. Development setup

Tested on Python 3.10, 3.11, and 3.12 (CI matrix). Lower versions
are unsupported because the codebase uses PEP 604 union syntax
(`int | None`).

```powershell
# Clone
git clone https://github.com/SHIRUIZHAOIILLiil/search-engine-tool.git
cd search-engine-tool

# Virtualenv (recommended)
python -m venv .venv
.venv\Scripts\Activate.ps1            # PowerShell
# source .venv/bin/activate           # bash / zsh

# Install runtime + dev dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` mirrors the CI install — it pulls in
`requirements.txt` (BeautifulSoup, requests) plus the dev tooling
(coverage, ruff, mypy, pdoc).

---

## 2. Running the toolchain locally

The three CI gates plus a few useful extras:

```powershell
# Tests (370+ at v1.7.0, no warnings tolerated)
python -W error -m unittest discover

# Test coverage report (must stay above 85 %; configured in pyproject)
python -m coverage run -m unittest discover
python -m coverage report

# Lint (ruff: pyflakes + pycodestyle + import sort + bug-bear)
python -m ruff check src/ tests/ benchmarks/

# Auto-fix the auto-fixable subset
python -m ruff check --fix src/ tests/ benchmarks/

# Static type check (mypy moderate strictness)
python -m mypy

# Benchmarks (out of CI — local only)
python -m benchmarks.run_benchmarks                # retrieval algos
python -m benchmarks.run_suggest_benchmark         # linear vs BK-tree

# Generated API docs (pdoc, output goes to docs/api/, gitignored)
python -m pdoc src --output-directory docs/api
```

All three CI gates run on every push to a feature branch or PR
against `main` — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## 3. Code style

### 3.1 Formatting and lint rules

`ruff` configuration lives in `pyproject.toml` under `[tool.ruff]`.
The curated rule set covers:

* `F` — pyflakes (unused imports, undefined names)
* `E`, `W` — pycodestyle errors and warnings (PEP 8)
* `I` — import sorting (replaces `isort`)
* `B` — flake8-bugbear (common real bugs)

`E501` (line length) is governed by `line-length = 100` rather than
the default 79. Test files have `F401` (unused imports) muted because
unittest's discovery sometimes leaves harmless re-imports.

### 3.2 Type hints

Every public function in `src/` has a return type annotation; most
have parameter annotations too. Mypy runs in moderate strictness
(see `[tool.mypy]`):

* `check_untyped_defs` — body-level checking even when signatures
  are partial.
* `warn_redundant_casts` — alerts on dead `typing.cast` calls.
* `warn_unused_ignores` — alerts on `# type: ignore` that no longer
  hides any error.
* `warn_unreachable` — alerts on statically dead code.
* `no_implicit_optional` — `param: int = None` is rejected; must
  write `param: int | None = None`.

`--strict` is deliberately *not* enabled. The data structures in
`indexer.py` use `TypedDict` for posting layouts; full strict mode
would force every test fixture to also use the TypedDict
constructor, which would obscure intent in the tests.

### 3.3 Docstrings

Every module gets a top-level docstring stating its purpose and
citing any non-obvious paper / textbook reference. Public functions
and classes get Google-style docstrings with `Args` / `Returns` /
`Raises` sections when non-trivial. `pdoc` consumes these directly
to produce `docs/api/`.

Private helpers (leading underscore) only need a one-line docstring
unless the algorithm is subtle enough to warrant explanation.

### 3.4 Naming

* Functions and variables: `snake_case`.
* Classes: `PascalCase`.
* Module-level constants: `UPPER_SNAKE_CASE`.
* Private helpers and internal cache attributes: `_leading_underscore`.

---

## 4. Commit conventions

### 4.1 Message format

**One line, Conventional Commits prefix**, no body. Prefixes used
in this repo:

* `feat:` — new behaviour visible to users / consumers.
* `fix:` — bug fix; tests that failed before now pass.
* `refactor:` — internal restructure with no behaviour change.
* `test:` — adding or improving tests.
* `docs:` — README, architecture, CONTRIBUTING, CHANGELOG, docstrings.
* `build:` — packaging, CI workflow, dependency manifests.
* `chore:` — repo hygiene that fits none of the above.

Optional scope in parentheses: `feat(crawler): reuse Session ...`.

Examples from the repo's history:

```
feat(retrieval): add skip-pointer optimization for conjunctive intersection
refactor(indexer): make save_index an atomic write
build(ci): enforce mypy type checking in CI
docs(architecture): add architecture overview document
```

### 4.2 Granularity

One **conceptually atomic change** per commit. If you can describe
the change in two short clauses joined by "and", consider splitting
it into two commits. The roadmap step preambles in chat history
demonstrate the granularity that works well — typically 3 to 5
commits per release.

### 4.3 Staging

Always stage explicit paths:

```
git add src/foo.py tests/test_foo.py
```

`git add -A`, `git add .`, and `git add -u` are discouraged — they
risk staging local artefacts (`data/index.json`, `.venv`, IDE
configs) that should not be committed.

---

## 5. Branch and release workflow

Each roadmap step lands as its own short-lived feature branch,
merged into `main` with `--no-ff` so the topology is visible in
`git log --graph`. Tags are annotated, named `vN.M.K`, and carry
a one-line release subject.

### 5.1 Starting a step

```
git switch main
git pull origin main
git switch -c feature/<short-name>-vN.M.K
```

Examples: `feature/snippets-v1.4.0`, `feature/bktree-v1.6.0`.

### 5.2 During the step

Make multiple small commits as above. Push freely if you want a
backup on the remote, but the branch is not consumed until merge.

### 5.3 Closing the step

```
# A. Land it locally
git switch main
git merge --no-ff feature/<short-name>-vN.M.K -m "Merge branch 'feature/<short-name>-vN.M.K'"
git tag -a vN.M.K -m "vN.M.K: <one-line release subject>"

# B. Push (this is where CI runs against the tag's tree)
git push origin main
git push origin vN.M.K

# C. Clean up the feature branch
git branch -d feature/<short-name>-vN.M.K
```

The push-before-delete order matters: `git branch -d` refuses if
the branch is not yet on `origin/main`, which protects you from
deleting work that has not been published yet.

---

## 6. Testing strategy

Add tests at the layer that matches the change:

* **Unit** (`tests/test_<module>.py`) — pure-function or
  one-class-in-isolation behaviour. Hand-build the `Index` /
  `CrawledPage` / fixtures directly; no real network, no real
  filesystem outside `TemporaryDirectory`.
* **Integration** (`tests/test_integration.py`) — when a change
  crosses module boundaries (crawler → parser → indexer → search),
  add an end-to-end case against the stub HTTP fixture.
* **Property** — when you add a new optimisation that should be
  semantically equivalent to an existing one. Set a fixed seed,
  generate ~20 randomised inputs, assert equivalence on each.
  Examples: `test_bktree.py::test_random_vocabulary_search_matches_linear_scan`,
  `test_retrieval.py::test_conjunctive_match_with_and_without_skip_agree`.
* **Performance** — only when there is a non-trivial regression
  risk on a hot path. Use generous budgets (10×+ typical) to avoid
  CI flakes.

Coverage must stay above 85 % overall — CI enforces this with
`--fail-under=85`. The current baseline is ~93 %.

---

## 7. Adding a feature without breaking the brief

The brief requires four commands (`build`, `load`, `print`, `find`)
with specific shapes:

* `find good friends` returns every page containing both `good`
  AND `friends`.
* `print nonsense` returns the posting list for the word.

Any new syntax / behaviour is **additive only** — it must layer on
top without changing what those exact commands do. Specifically:

1. **Test the brief case explicitly.** Whenever you add a new
   `find` syntax (`field=value` facets, `"quoted phrase"`, …), add
   a test that pins `find good friends` to its v1.0.0 result. See
   `tests/test_main.py::test_find_without_equals_preserves_brief_conjunctive_path`
   for the pattern.
2. **Route by syntax marker.** Choose a marker that does not appear
   in plain queries — quoted strings, `=` for facets — and dispatch
   only on that marker. Plain words flow through the unchanged path.
3. **Document in the right places.**
   * README **Features** bullet + **Usage** example.
   * `docs/architecture.md` if you added a module or a new pipeline
     stage.
   * `CHANGELOG.md` entry under the next version tag.
   * Docstrings on every new public function.

---

## 8. Schema changes

Bumping `INDEX_VERSION` (in `src/indexer.py`) is a breaking change
for users with on-disk `index.json` files. The version guard in
`load_index` rejects old files with a clear "rebuild" error — that
is the contract.

Before bumping:

1. Confirm the change cannot fit in an additive field (a new optional
   key with a sensible default usually can).
2. Update the **schema evolution table** in
   [`docs/architecture.md`](docs/architecture.md) §5 with the new
   version and what changed.
3. Note the breaking change explicitly in the next CHANGELOG entry
   so users know to rebuild after `pull`.
4. Add a test that pins the new field's load / save roundtrip.

---

## 9. Documentation cross-references

When you land a feature, update:

| File | When |
|---|---|
| `README.md` | Always — at minimum a Features bullet. Usage example if user-visible behaviour changed. |
| `CHANGELOG.md` | Always — one entry per release tag, under the new version heading. |
| `docs/architecture.md` | When you add a module, change a pipeline stage, or introduce a new design pattern. |
| Inline docstrings | Whenever you add a public function, class, or module. Cite the textbook / paper if the algorithm is non-trivial. |
| `CONTRIBUTING.md` (this file) | When you add a new tool to the toolchain or change the workflow. |

---

## 10. Questions and follow-ups

This is a coursework project, not a maintained library — the
issue tracker is mostly for the author's own use. If something is
unclear when you read this, the answers are most likely in the
roadmap-step preambles in the project's chat history or the
docstrings of the relevant module. The architecture document is
the canonical reference for *how the parts fit together*; this
file is the canonical reference for *how to add a new part*.
