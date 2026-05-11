"""Benchmark Lecture-13 retrieval algorithms across corpus sizes.

Compares the four retrieval algorithms implemented in
:mod:`src.retrieval` on synthetic corpora of varying scale, reporting
wall-clock time and peak memory usage. Results land in
``benchmarks/results/`` as terminal output plus JSON, CSV, and a
report-ready Markdown table.

The benchmark separates two algorithmic *groups* whose outputs are
not comparable:

* **Group A — ranked retrieval.** ``document_at_a_time`` and
  ``term_at_a_time`` produce ``(doc_id, score)`` lists. Each is timed
  with both :class:`~src.ranker.TFIDFRanker` and
  :class:`~src.ranker.BM25Ranker` to expose the per-call scoring
  overhead.
* **Group B - intersection only.** ``conjunctive_match`` and
  ``conjunctive_match_with_skip`` return raw doc-id lists. Comparing
  these against the Group A rankers would be misleading — Group B
  does no scoring, so it will always be faster regardless of the
  intersection algorithm's actual quality.

Three query *shapes* exercise the Lecture-13 trade-offs:

* ``single_common`` — one high-frequency token (baseline).
* ``multi_balanced`` — two medium-frequency tokens (worst case for
  TAAT, whose accumulator dictionary grows with the union of every
  posting list).
* ``skewed_rare_common`` — one rare token plus one common token (the
  canonical skip-pointer win case — L13 slide 18-23).

Each shape contributes three instances drawn from the synthetic
vocabulary so the report shows within-shape variance rather than a
single point estimate.

Time and memory are measured in **separate passes** — tracemalloc
adds 5-10x overhead to the code under test, so mixing the two would
contaminate the timing numbers. Each timing cell runs once for warmup
(discarded) plus five measured repetitions; the table reports the
median and inter-quartile range across the five.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import socket
import statistics
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from benchmarks.corpus import synthesize_pages
from src.indexer import Index, build_index
from src.ranker import BM25Ranker, Ranker, TFIDFRanker
from src.retrieval import (
    conjunctive_match,
    conjunctive_match_with_skip,
    document_at_a_time,
    term_at_a_time,
)

# Number of times each measured cell is timed; the first run is a
# discarded warmup. 5 measured reps strikes a balance between noise
# (too few) and total wall-clock cost (too many). Honoured for the
# memory pass too, but tracemalloc results are deterministic for our
# pure-Python code, so the memory pass runs a single rep per cell.
DEFAULT_REPS = 5
DEFAULT_SIZES = (250, 500, 1000, 2000)
QUICK_SIZES = (50, 100)
QUICK_REPS = 2

# Top-k cut-off used for the ranked retrieval algorithms. The cost of
# the top-k heap (Group A) is O(N log k); reporting a fixed k keeps
# the comparison fair across sizes.
TOP_K = 10


@dataclass
class CellResult:
    """One timing or memory measurement for one (algo, query, size) cell."""

    algorithm: str
    query_shape: str
    query_instance: int
    size: int
    metric: str
    value: float
    unit: str
    n_samples: int


@dataclass
class BenchmarkReport:
    """Full report — metadata block + every measurement."""

    metadata: dict
    cells: list[CellResult] = field(default_factory=list)


# --------------------------------------------------------------------- #
# Query selection                                                       #
# --------------------------------------------------------------------- #


def select_queries(
    index: Index,
    instances_per_shape: int = 3,
) -> dict[str, list[list[str]]]:
    """Pick representative queries from the index's actual vocabulary.

    Hardcoding query tokens (e.g. always ``word0042``) would couple
    the benchmark to the specific synthesis seed. Selecting at runtime
    from the index's term-frequency distribution keeps the comparison
    meaningful across reseeded runs.

    Buckets terms by posting-list length:

    * ``common`` — top tertile (appears in many docs).
    * ``mid``   — middle tertile.
    * ``rare``  — bottom tertile.

    Then composes:

    * ``single_common`` — 1 common term per instance.
    * ``multi_balanced`` — 2 mid terms per instance.
    * ``skewed_rare_common`` — 1 rare + 1 common per instance.
    """
    if not index.postings:
        return {
            "single_common": [],
            "multi_balanced": [],
            "skewed_rare_common": [],
        }

    by_freq = sorted(
        index.postings.items(),
        key=lambda kv: len(kv[1]),
        reverse=True,
    )
    n = len(by_freq)
    third = max(1, n // 3)
    common = [term for term, _ in by_freq[:third]]
    mid = [term for term, _ in by_freq[third:2 * third]]
    rare = [term for term, _ in by_freq[2 * third:]]

    def pick(pool: list[str], i: int) -> str:
        # Stride through the pool deterministically so successive
        # instances pull distinct tokens rather than always the most
        # extreme one.
        return pool[(i * 7) % len(pool)] if pool else "missing"

    shapes: dict[str, list[list[str]]] = {
        "single_common": [],
        "multi_balanced": [],
        "skewed_rare_common": [],
    }
    for i in range(instances_per_shape):
        shapes["single_common"].append([pick(common, i)])
        shapes["multi_balanced"].append([pick(mid, i), pick(mid, i + 1)])
        shapes["skewed_rare_common"].append([pick(rare, i), pick(common, i)])
    return shapes


# --------------------------------------------------------------------- #
# Algorithm drivers                                                     #
# --------------------------------------------------------------------- #


def _ranked_driver(
    index: Index,
    tokens: list[str],
    algorithm: Callable,
    ranker: Ranker,
) -> int:
    """Run a ranked-retrieval algorithm; return result length.

    The return value is used solely to defeat dead-code elimination —
    in CPython today this is overkill, but staying explicit makes the
    intent obvious to a reader and protects against future
    optimisations.
    """
    return len(algorithm(index, tokens, ranker, top_k=TOP_K))


def _intersect_driver(
    index: Index,
    tokens: list[str],
    algorithm: Callable,
) -> int:
    return len(algorithm(index, tokens))


# (display name, callable, group, optional ranker)
ALGORITHMS: list[tuple[str, Callable, str, Ranker | None]] = [
    ("DAAT+TFIDF", document_at_a_time, "ranked", TFIDFRanker()),
    ("DAAT+BM25", document_at_a_time, "ranked", BM25Ranker()),
    ("TAAT+TFIDF", term_at_a_time, "ranked", TFIDFRanker()),
    ("TAAT+BM25", term_at_a_time, "ranked", BM25Ranker()),
    ("Conjunct (naive)", conjunctive_match, "intersect", None),
    ("Conjunct (skip)", conjunctive_match_with_skip, "intersect", None),
]


# --------------------------------------------------------------------- #
# Measurement passes                                                    #
# --------------------------------------------------------------------- #


def _time_one(
    index: Index,
    tokens: list[str],
    algorithm: Callable,
    ranker: Ranker | None,
    reps: int,
) -> list[float]:
    """Run the algorithm ``reps + 1`` times, discard warmup, return seconds.

    Wrapping the measurement loop in a closure (rather than measuring
    around a single call) lets ``perf_counter`` resolution dominate
    only once per measured rep, not once per overhead. The warmup
    iteration absorbs first-call costs like ``functools.lru_cache``
    population, dict resizing, or any one-off allocations.
    """
    def call() -> int:
        if ranker is None:
            return _intersect_driver(index, tokens, algorithm)
        return _ranked_driver(index, tokens, algorithm, ranker)

    # Warmup — discarded.
    call()

    timings: list[float] = []
    for _ in range(reps):
        start = time.perf_counter()
        call()
        timings.append(time.perf_counter() - start)
    return timings


def _memory_one(
    index: Index,
    tokens: list[str],
    algorithm: Callable,
    ranker: Ranker | None,
) -> int:
    """Peak heap bytes allocated during one call.

    ``tracemalloc`` adds 5-10x runtime overhead — that is the entire
    reason memory and time are measured in separate passes. A single
    rep is enough because our retrieval algorithms are pure-Python
    over deterministic inputs, so peak memory is constant across runs.
    """
    tracemalloc.start()
    if ranker is None:
        _intersect_driver(index, tokens, algorithm)
    else:
        _ranked_driver(index, tokens, algorithm, ranker)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def measure(
    index: Index,
    queries: dict[str, list[list[str]]],
    size: int,
    reps: int,
) -> list[CellResult]:
    """Run time + memory passes for every (algo, query) on one index."""
    cells: list[CellResult] = []

    for algo_name, algo, group, ranker in ALGORITHMS:
        for shape, instances in queries.items():
            for instance_idx, tokens in enumerate(instances):
                timings = _time_one(index, tokens, algo, ranker, reps)
                median = statistics.median(timings)
                # IQR collapses to 0 for n < 4; quartiles would raise.
                if len(timings) >= 4:
                    quartiles = statistics.quantiles(timings, n=4)
                    iqr = quartiles[2] - quartiles[0]
                else:
                    iqr = 0.0

                cells.append(CellResult(
                    algorithm=algo_name,
                    query_shape=shape,
                    query_instance=instance_idx,
                    size=size,
                    metric="time_median_seconds",
                    value=median,
                    unit="s",
                    n_samples=len(timings),
                ))
                cells.append(CellResult(
                    algorithm=algo_name,
                    query_shape=shape,
                    query_instance=instance_idx,
                    size=size,
                    metric="time_iqr_seconds",
                    value=iqr,
                    unit="s",
                    n_samples=len(timings),
                ))

                peak_bytes = _memory_one(index, tokens, algo, ranker)
                cells.append(CellResult(
                    algorithm=algo_name,
                    query_shape=shape,
                    query_instance=instance_idx,
                    size=size,
                    metric="memory_peak_bytes",
                    value=float(peak_bytes),
                    unit="B",
                    n_samples=1,
                ))

        # No-op for the variable to make group an obvious read for
        # anyone scanning the loop body — we recompute group via the
        # algorithm tuple in the output stage instead.
        _ = group

    return cells


# --------------------------------------------------------------------- #
# Output                                                                #
# --------------------------------------------------------------------- #


def _algo_group(algo_name: str) -> str:
    for name, _, group, _ in ALGORITHMS:
        if name == algo_name:
            return group
    return "unknown"


def _aggregate(
    cells: list[CellResult],
    metric: str,
) -> dict[tuple[str, str, int], float]:
    """Average ``metric`` over query instances within each (algo, shape, size)."""
    bucket: dict[tuple[str, str, int], list[float]] = {}
    for c in cells:
        if c.metric != metric:
            continue
        bucket.setdefault((c.algorithm, c.query_shape, c.size), []).append(c.value)
    return {k: statistics.mean(v) for k, v in bucket.items()}


def render_terminal_table(report: BenchmarkReport) -> str:
    """Pretty-print a side-by-side table for terminal viewing.

    One row per (algo, query shape); one column per size; values are
    median wall-clock time averaged across query instances. Ranked
    and intersect groups are printed as separate sub-tables so the
    reader does not mistakenly compare ranked vs intersect numbers.
    """
    times = _aggregate(report.cells, "time_median_seconds")
    sizes = sorted({k[2] for k in times})
    shapes = ["single_common", "multi_balanced", "skewed_rare_common"]

    lines: list[str] = []
    for group, group_label in [("ranked", "Group A - ranked retrieval (top-10)"),
                                ("intersect", "Group B - intersection only")]:
        algos = [name for name, _, g, _ in ALGORITHMS if g == group]
        lines.append("")
        lines.append(group_label)
        lines.append("=" * len(group_label))
        header = f"{'algorithm':<20}{'query shape':<22}" + "".join(
            f"{s:>12}" for s in sizes
        )
        lines.append(header)
        lines.append("-" * len(header))
        for algo in algos:
            for shape in shapes:
                row_cells = []
                for s in sizes:
                    v = times.get((algo, shape, s))
                    row_cells.append(
                        f"{v * 1000:>11.3f}m" if v is not None else f"{'-':>12}"
                    )
                lines.append(
                    f"{algo:<20}{shape:<22}" + "".join(row_cells)
                )
        lines.append("")
    lines.append("Times are median milliseconds (lower is better), "
                 "averaged over 3 query instances per shape.")
    lines.append("See benchmarks/results/*.{json,csv,md} for raw data, "
                 "IQR, and memory.")
    return "\n".join(lines)


def render_markdown(report: BenchmarkReport) -> str:
    """Report-ready Markdown — paste straight into the dissertation."""
    times = _aggregate(report.cells, "time_median_seconds")
    mem = _aggregate(report.cells, "memory_peak_bytes")
    sizes = sorted({k[2] for k in times})
    shapes = ["single_common", "multi_balanced", "skewed_rare_common"]

    md: list[str] = []
    md.append("# Retrieval Algorithm Benchmark")
    md.append("")
    md.append("## Run metadata")
    md.append("")
    for k, v in report.metadata.items():
        md.append(f"- **{k}**: `{v}`")
    md.append("")

    for group, label in [("ranked", "Group A - Ranked Retrieval (top-10)"),
                         ("intersect", "Group B - Intersection Only")]:
        algos = [name for name, _, g, _ in ALGORITHMS if g == group]
        md.append(f"## {label}")
        md.append("")
        md.append("### Median time (ms)")
        md.append("")
        header = "| algorithm | query shape | " + " | ".join(
            f"n={s}" for s in sizes
        ) + " |"
        sep = "|" + "|".join(["---"] * (2 + len(sizes))) + "|"
        md.append(header)
        md.append(sep)
        for algo in algos:
            for shape in shapes:
                row = [algo, shape]
                for s in sizes:
                    v = times.get((algo, shape, s))
                    row.append(f"{v * 1000:.3f}" if v is not None else "-")
                md.append("| " + " | ".join(row) + " |")
        md.append("")
        md.append("### Peak memory (KiB)")
        md.append("")
        md.append(header)
        md.append(sep)
        for algo in algos:
            for shape in shapes:
                row = [algo, shape]
                for s in sizes:
                    v = mem.get((algo, shape, s))
                    row.append(f"{v / 1024:.1f}" if v is not None else "-")
                md.append("| " + " | ".join(row) + " |")
        md.append("")
    return "\n".join(md)


def write_json(report: BenchmarkReport, path: Path) -> None:
    payload = {
        "metadata": report.metadata,
        "cells": [asdict(c) for c in report.cells],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(report: BenchmarkReport, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "algorithm", "group", "query_shape", "query_instance",
            "size", "metric", "value", "unit", "n_samples",
        ])
        for c in report.cells:
            writer.writerow([
                c.algorithm, _algo_group(c.algorithm),
                c.query_shape, c.query_instance,
                c.size, c.metric, c.value, c.unit, c.n_samples,
            ])


def write_markdown(report: BenchmarkReport, path: Path) -> None:
    path.write_text(render_markdown(report), encoding="utf-8")


# --------------------------------------------------------------------- #
# Metadata                                                              #
# --------------------------------------------------------------------- #


def collect_metadata(sizes: list[int], reps: int) -> dict:
    """Capture run-environment context for reproducibility."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sha = "unknown"

    return {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "hostname": socket.gethostname(),
        "git_sha": sha,
        "sizes": sizes,
        "reps": reps,
        "top_k": TOP_K,
        "algorithms": [name for name, _, _, _ in ALGORITHMS],
        "query_shapes": ["single_common", "multi_balanced", "skewed_rare_common"],
    }


# --------------------------------------------------------------------- #
# Top-level entry point                                                 #
# --------------------------------------------------------------------- #


def run(
    sizes: list[int],
    reps: int,
    output_dir: Path,
    instances_per_shape: int = 3,
    progress: Callable[[str], None] = print,
) -> BenchmarkReport:
    """Run the full benchmark sweep and write all outputs.

    Splitting the CLI shell out of the orchestration body lets the
    test suite call ``run`` directly with tiny inputs — no argparse
    plumbing, no subprocess, no stdout capture.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = collect_metadata(sizes, reps)
    report = BenchmarkReport(metadata=metadata)

    for size in sizes:
        progress(f"Synthesising {size}-page corpus...")
        pages = synthesize_pages(size)
        progress(f"Building index for n={size}...")
        index = build_index(pages)
        queries = select_queries(index, instances_per_shape=instances_per_shape)
        progress(f"Measuring n={size} "
                 f"({len(ALGORITHMS)} algos x "
                 f"{sum(len(v) for v in queries.values())} queries)...")
        report.cells.extend(measure(index, queries, size, reps))

    ts = metadata["run_timestamp_utc"].replace(":", "-")
    write_json(report, output_dir / f"benchmark-{ts}.json")
    write_csv(report, output_dir / f"benchmark-{ts}.csv")
    write_markdown(report, output_dir / f"benchmark-{ts}.md")

    progress("")
    progress(render_terminal_table(report))
    progress("")
    progress(f"Results written to {output_dir}/benchmark-{ts}.{{json,csv,md}}")

    return report


def _parse_sizes(spec: str) -> list[int]:
    out = [int(s) for s in spec.split(",") if s.strip()]
    if not out:
        raise argparse.ArgumentTypeError("--sizes must be a non-empty comma list")
    if any(s <= 0 for s in out):
        raise argparse.ArgumentTypeError("--sizes entries must be positive")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.run_benchmarks",
        description="Benchmark Lecture-13 retrieval algorithms.",
    )
    parser.add_argument(
        "--sizes",
        type=_parse_sizes,
        default=list(DEFAULT_SIZES),
        help=f"Comma-separated corpus sizes (default: {','.join(map(str, DEFAULT_SIZES))})",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=DEFAULT_REPS,
        help=f"Measured repetitions per cell, after one warmup (default: {DEFAULT_REPS})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/results"),
        help="Directory to write JSON/CSV/Markdown results into",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=f"Fast mode for development: sizes={QUICK_SIZES}, reps={QUICK_REPS}",
    )
    args = parser.parse_args(argv)

    if args.quick:
        args.sizes = list(QUICK_SIZES)
        args.reps = QUICK_REPS

    run(sizes=args.sizes, reps=args.reps, output_dir=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
