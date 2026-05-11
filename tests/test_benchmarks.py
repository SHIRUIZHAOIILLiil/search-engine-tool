"""Tests for the benchmark support modules.

The benchmark scripts under ``benchmarks/`` are not exercised on CI
for runtime budget reasons, but the helpers they depend on are tested
here so a refactor cannot silently break the corpus contract.

The runner's full sweep is also too slow for CI; we cover it with a
smoke test that drives one tiny corpus through the whole pipeline,
asserting the output schema rather than the timing numbers.
"""

import csv
import io
import json
import random
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from benchmarks.corpus import (
    DEFAULT_VOCAB_SIZE,
    make_typo,
    synthesize_clustered_vocabulary,
    synthesize_pages,
    synthesize_vocabulary,
)
from benchmarks.run_benchmarks import (
    ALGORITHMS,
    main,
    run,
    select_queries,
)
from benchmarks.run_suggest_benchmark import main as suggest_main
from benchmarks.run_suggest_benchmark import run as suggest_run
from src.indexer import build_index


class SynthesizePagesTests(unittest.TestCase):
    def test_synthesize_pages_is_deterministic(self):
        # Same seed, same output — benchmark numbers across runs are
        # only comparable if the workload is byte-identical.
        first = synthesize_pages(50, seed=42)
        second = synthesize_pages(50, seed=42)
        self.assertEqual(len(first), len(second))
        # strict=True is safe here — we already asserted equal length
        # above; the explicit flag silences ruff B905 and pins the
        # invariant for future readers.
        for page_a, page_b in zip(first, second, strict=True):
            self.assertEqual(page_a.url, page_b.url)
            self.assertEqual(page_a.text, page_b.text)

    def test_different_seeds_produce_different_text(self):
        # Sanity check the RNG actually responds to the seed — guards
        # against accidentally hard-coding a single random stream.
        a = synthesize_pages(20, seed=1)
        b = synthesize_pages(20, seed=2)
        self.assertNotEqual(
            [page.text for page in a],
            [page.text for page in b],
        )

    def test_synthesize_pages_size_and_url_uniqueness(self):
        pages = synthesize_pages(100)
        self.assertEqual(len(pages), 100)
        urls = [page.url for page in pages]
        self.assertEqual(len(set(urls)), 100, "URLs must be unique")

    def test_synthesize_pages_tokens_come_from_vocab(self):
        pages = synthesize_pages(30)
        expected_vocab = {f"word{i:04d}" for i in range(DEFAULT_VOCAB_SIZE)}
        for page in pages:
            for token in page.text.split():
                self.assertIn(token, expected_vocab)

    def test_synthesize_pages_respects_length_bounds(self):
        pages = synthesize_pages(40, tokens_per_page=(10, 15))
        for page in pages:
            n_tokens = len(page.text.split())
            self.assertGreaterEqual(n_tokens, 10)
            self.assertLessEqual(n_tokens, 15)

    def test_synthesize_pages_zero_returns_empty(self):
        # Edge case — generators that crash on n=0 are a frequent
        # source of off-by-one surprises in driver scripts.
        self.assertEqual(synthesize_pages(0), [])

    def test_synthesize_pages_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            synthesize_pages(-1)
        with self.assertRaises(ValueError):
            synthesize_pages(10, vocab_size=0)
        with self.assertRaises(ValueError):
            synthesize_pages(10, tokens_per_page=(5, 3))


class SelectQueriesTests(unittest.TestCase):
    def test_select_queries_returns_three_shapes_with_requested_instances(self):
        pages = synthesize_pages(40)
        index = build_index(pages)
        queries = select_queries(index, instances_per_shape=3)
        self.assertEqual(
            set(queries.keys()),
            {"single_common", "multi_balanced", "skewed_rare_common"},
        )
        for shape, instances in queries.items():
            self.assertEqual(len(instances), 3, f"{shape} should have 3 instances")
            for tokens in instances:
                self.assertTrue(tokens, f"{shape} instance must be non-empty")

    def test_select_queries_skewed_uses_rare_then_common(self):
        pages = synthesize_pages(40)
        index = build_index(pages)
        queries = select_queries(index, instances_per_shape=1)
        skewed = queries["skewed_rare_common"][0]
        # 2-token query: rare term first, common term second. We do
        # not assert specific tokens (they depend on the synth seed)
        # but the rare term must have a strictly shorter posting list
        # than the common term — that is the whole point of "skewed".
        rare_len = len(index.postings[skewed[0]])
        common_len = len(index.postings[skewed[1]])
        self.assertLess(rare_len, common_len)

    def test_select_queries_on_empty_index_returns_empty_shapes(self):
        empty_pages = synthesize_pages(0)
        index = build_index(empty_pages)
        queries = select_queries(index)
        for instances in queries.values():
            self.assertEqual(instances, [])


class BenchmarkRunnerSmokeTests(unittest.TestCase):
    """Tiny end-to-end run; asserts output shape, not timing values."""

    def test_run_produces_json_csv_and_markdown_with_expected_schema(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = run(
                sizes=[20],
                reps=2,
                output_dir=out,
                instances_per_shape=1,
                progress=lambda _msg: None,  # silence the smoke run
            )

            json_files = list(out.glob("benchmark-*.json"))
            csv_files = list(out.glob("benchmark-*.csv"))
            md_files = list(out.glob("benchmark-*.md"))
            self.assertEqual(len(json_files), 1)
            self.assertEqual(len(csv_files), 1)
            self.assertEqual(len(md_files), 1)

            payload = json.loads(json_files[0].read_text(encoding="utf-8"))
            self.assertIn("metadata", payload)
            self.assertIn("cells", payload)
            for key in (
                "run_timestamp_utc", "python_version", "platform",
                "git_sha", "sizes", "reps", "algorithms", "query_shapes",
            ):
                self.assertIn(key, payload["metadata"])

            with csv_files[0].open(encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0], [
                "algorithm", "group", "query_shape", "query_instance",
                "size", "metric", "value", "unit", "n_samples",
            ])
            self.assertGreater(len(rows), 1)

            md = md_files[0].read_text(encoding="utf-8")
            self.assertIn("Group A", md)
            self.assertIn("Group B", md)
            self.assertIn("| algorithm |", md)

            algos_in_report = {c.algorithm for c in report.cells}
            expected_algos = {name for name, _, _, _ in ALGORITHMS}
            self.assertEqual(algos_in_report, expected_algos)

            shapes_in_report = {c.query_shape for c in report.cells}
            self.assertEqual(shapes_in_report, {
                "single_common", "multi_balanced", "skewed_rare_common",
            })

    def test_main_cli_quick_mode_runs(self):
        # Exercises argparse + the --quick shortcut end-to-end; the
        # tiny sizes keep it CI-safe. stdout is captured because the
        # runner's pretty-printed table would otherwise dominate the
        # test output.
        with TemporaryDirectory() as tmp:
            with redirect_stdout(io.StringIO()):
                rc = main(["--quick", "--output", tmp])
            self.assertEqual(rc, 0)
            self.assertTrue(list(Path(tmp).glob("benchmark-*.json")))


class SynthesizeVocabularyTests(unittest.TestCase):
    """v1.6.0: vocabulary generators for the suggest benchmark."""

    def test_random_vocabulary_is_deterministic_under_same_seed(self):
        first = synthesize_vocabulary(50, seed=42)
        second = synthesize_vocabulary(50, seed=42)
        self.assertEqual(first, second)

    def test_random_vocabulary_returns_requested_size(self):
        vocab = synthesize_vocabulary(80)
        self.assertEqual(len(vocab), 80)
        # All entries unique by virtue of set-backed generation.
        self.assertEqual(len(set(vocab)), 80)

    def test_random_vocabulary_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            synthesize_vocabulary(-1)
        with self.assertRaises(ValueError):
            synthesize_vocabulary(10, word_length_range=(5, 2))

    def test_clustered_vocabulary_is_deterministic_under_same_seed(self):
        first = synthesize_clustered_vocabulary(100, seed=42)
        second = synthesize_clustered_vocabulary(100, seed=42)
        self.assertEqual(first, second)

    def test_clustered_vocabulary_words_share_stems(self):
        # The whole point of "clustered" is that several vocabulary
        # terms share a common prefix (their stem). Verify by checking
        # that the unique-prefix count is significantly less than the
        # vocabulary size.
        vocab = synthesize_clustered_vocabulary(200)
        prefixes_3char = {word[:3] for word in vocab if len(word) >= 3}
        # 200 words mapped to <100 distinct 3-char prefixes is "clustered".
        self.assertLess(len(prefixes_3char), 100)


class MakeTypoTests(unittest.TestCase):
    def test_typo_is_short_distance_from_source(self):
        rng = random.Random(0)
        for original in ("friend", "wisdom", "knowledge", "x"):
            target = make_typo(original, n_edits=1, rng=rng)
            # One random edit is at most 1 edit away. We cannot
            # assert exactly 1 because delete on a length-1 string
            # is a no-op (special case in make_typo's contract).
            from src.suggest import levenshtein_distance
            self.assertLessEqual(levenshtein_distance(target, original), 1)

    def test_typo_rejects_invalid_inputs(self):
        rng = random.Random(0)
        with self.assertRaises(ValueError):
            make_typo("word", n_edits=-1, rng=rng)
        with self.assertRaises(ValueError):
            make_typo("", n_edits=1, rng=rng)


class SuggestBenchmarkRunnerSmokeTests(unittest.TestCase):
    def test_run_produces_json_csv_and_markdown(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = suggest_run(
                sizes=[40],
                reps=2,
                n_targets=5,
                output_dir=out,
                style="clustered",
                progress=lambda _msg: None,
            )

            self.assertEqual(len(list(out.glob("suggest-benchmark-*.json"))), 1)
            self.assertEqual(len(list(out.glob("suggest-benchmark-*.csv"))), 1)
            self.assertEqual(len(list(out.glob("suggest-benchmark-*.md"))), 1)

            algos_in_report = {c.algorithm for c in report.cells}
            self.assertEqual(algos_in_report, {"linear", "bktree"})
            metrics_in_report = {c.metric for c in report.cells}
            self.assertIn("time_median_seconds", metrics_in_report)
            self.assertIn("memory_peak_bytes", metrics_in_report)

    def test_run_rejects_unknown_style(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                suggest_run(
                    sizes=[20],
                    reps=2,
                    n_targets=3,
                    output_dir=Path(tmp),
                    style="nonexistent",
                    progress=lambda _msg: None,
                )

    def test_main_cli_quick_mode_runs(self):
        with TemporaryDirectory() as tmp:
            with redirect_stdout(io.StringIO()):
                rc = suggest_main(["--quick", "--output", tmp])
            self.assertEqual(rc, 0)
            self.assertTrue(list(Path(tmp).glob("suggest-benchmark-*.json")))

    def test_main_cli_random_style_is_supported(self):
        with TemporaryDirectory() as tmp:
            with redirect_stdout(io.StringIO()):
                rc = suggest_main([
                    "--quick", "--output", tmp, "--style", "random",
                ])
            self.assertEqual(rc, 0)
            json_files = list(Path(tmp).glob("suggest-benchmark-*.json"))
            self.assertEqual(len(json_files), 1)
            payload = json.loads(json_files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["vocab_style"], "random")


if __name__ == "__main__":
    unittest.main()
