"""Benchmark suggest_corrections: linear scan vs BK-tree.

Compares the two implementations of vocabulary-based spelling
correction added across v1.2.0 (linear scan) and v1.6.0 (BK-tree)
on synthetic vocabularies of varying size. The runner mirrors the
methodology of :mod:`benchmarks.run_benchmarks` (warmup, IQR,
time/memory separate passes, JSON/CSV/Markdown outputs) so the two
benchmark surfaces stay structurally consistent.

Default sweep: vocabularies of 100, 500, 2 000 and 5 000 random
words — straddling :data:`src.suggest.BKTREE_MIN_VOCAB` so the
report shows where the BK-tree starts paying its build cost back.
Each cell drives the implementations with 50 typo targets generated
from random vocabulary terms; the targets are identical between
algorithms within a cell so the comparison is apples to apples.

Run::

    python -m benchmarks.run_suggest_benchmark
    python -m benchmarks.run_suggest_benchmark --quick
    python -m benchmarks.run_suggest_benchmark --sizes 200,1000
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import random
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

from benchmarks.corpus import (
    make_typo,
    synthesize_clustered_vocabulary,
    synthesize_vocabulary,
)
from src.bktree import BKTree
from src.suggest import (
    _suggest_via_bktree,
    _suggest_via_linear_scan,
    levenshtein_distance,
)

DEFAULT_SIZES = (100, 500, 2000, 5000)
QUICK_SIZES = (50, 200)
DEFAULT_REPS = 5
QUICK_REPS = 2
DEFAULT_N_TARGETS = 50
QUICK_N_TARGETS = 10
DEFAULT_MAX_DISTANCE = 2
DEFAULT_STYLE = "clustered"
TARGET_SEED = 20260601

# Vocabulary generators. Clustered (the default) models real English
# morphology — ``friend / friends / friendly`` — where BK-tree's
# triangle-inequality pruning is most effective. Random uniform
# strings are kept as the alternative because they exercise the
# worst-case for BK-tree and document the algorithm's limits.
_VOCAB_GENERATORS = {
    "clustered": synthesize_clustered_vocabulary,
    "random": synthesize_vocabulary,
}


@dataclass
class CellResult:
    """One measurement for one (algorithm, vocab_size, metric)."""

    algorithm: str
    vocab_size: int
    n_targets: int
    metric: str
    value: float
    unit: str
    n_samples: int


@dataclass
class SuggestBenchmarkReport:
    metadata: dict
    cells: list[CellResult] = field(default_factory=list)


# --------------------------------------------------------------------- #
# Inputs                                                                #
# --------------------------------------------------------------------- #


def build_targets(vocabulary: list[str], n_targets: int) -> list[str]:
    """Sample ``n_targets`` vocab words and apply one random edit each.

    Each target is therefore within edit distance 1 of a known
    vocabulary term, so :func:`_suggest_via_linear_scan` and
    :func:`_suggest_via_bktree` both return non-trivial results —
    the benchmark exercises the *interesting* code paths, not the
    near-instant empty-result path.
    """
    rng = random.Random(TARGET_SEED)
    n_targets = min(n_targets, len(vocabulary))
    sources = rng.sample(vocabulary, n_targets) if vocabulary else []
    return [make_typo(word, n_edits=1, rng=rng) for word in sources]


# --------------------------------------------------------------------- #
# Drivers                                                               #
# --------------------------------------------------------------------- #


def _linear_driver(targets: list[str], vocab: list[str], vocab_set: set[str]) -> int:
    """Run the linear scan over every target; return result count.

    The return is used purely as a dead-code-elimination guard — a
    side-effect-free function returning the same value every call
    could in theory be hoisted out of a measurement loop by an
    aggressive optimiser. CPython does not do this today, but
    staying explicit is cheap.
    """
    out = _suggest_via_linear_scan(
        targets, vocab, vocab_set,
        max_distance=DEFAULT_MAX_DISTANCE,
        max_suggestions=3,
    )
    return len(out)


def _bktree_driver(targets: list[str], vocab_set: set[str], tree: BKTree) -> int:
    out = _suggest_via_bktree(
        targets, vocab_set, tree,
        max_distance=DEFAULT_MAX_DISTANCE,
        max_suggestions=3,
    )
    return len(out)


# --------------------------------------------------------------------- #
# Measurement                                                           #
# --------------------------------------------------------------------- #


def _time_call(call: Callable[[], int], reps: int) -> list[float]:
    """One warmup + ``reps`` measured calls, returning seconds each."""
    call()  # warmup
    timings: list[float] = []
    for _ in range(reps):
        start = time.perf_counter()
        call()
        timings.append(time.perf_counter() - start)
    return timings


def _memory_call(call: Callable[[], int]) -> int:
    tracemalloc.start()
    call()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def measure(vocabulary: list[str], n_targets: int, reps: int) -> list[CellResult]:
    """Time + memory for both algorithms on one vocabulary size."""
    vocab_set = set(vocabulary)
    targets = build_targets(vocabulary, n_targets)

    # BK-tree is built ONCE outside the measured region — we measure
    # query cost only, since the build is amortised across many
    # calls in the production cache pattern.
    tree = BKTree(levenshtein_distance, vocabulary)

    def linear_call() -> int:
        return _linear_driver(targets, vocabulary, vocab_set)

    def bktree_call() -> int:
        return _bktree_driver(targets, vocab_set, tree)

    results: list[CellResult] = []
    for algo_name, call in (("linear", linear_call), ("bktree", bktree_call)):
        timings = _time_call(call, reps)
        median = statistics.median(timings)
        iqr = (
            statistics.quantiles(timings, n=4)[2]
            - statistics.quantiles(timings, n=4)[0]
            if len(timings) >= 4
            else 0.0
        )
        peak_bytes = _memory_call(call)

        results.append(CellResult(
            algorithm=algo_name,
            vocab_size=len(vocabulary),
            n_targets=len(targets),
            metric="time_median_seconds",
            value=median,
            unit="s",
            n_samples=len(timings),
        ))
        results.append(CellResult(
            algorithm=algo_name,
            vocab_size=len(vocabulary),
            n_targets=len(targets),
            metric="time_iqr_seconds",
            value=iqr,
            unit="s",
            n_samples=len(timings),
        ))
        results.append(CellResult(
            algorithm=algo_name,
            vocab_size=len(vocabulary),
            n_targets=len(targets),
            metric="memory_peak_bytes",
            value=float(peak_bytes),
            unit="B",
            n_samples=1,
        ))
    return results


# --------------------------------------------------------------------- #
# Output                                                                #
# --------------------------------------------------------------------- #


def _by_metric(
    cells: list[CellResult], metric: str
) -> dict[tuple[str, int], float]:
    return {
        (c.algorithm, c.vocab_size): c.value
        for c in cells
        if c.metric == metric
    }


def render_terminal(report: SuggestBenchmarkReport) -> str:
    times = _by_metric(report.cells, "time_median_seconds")
    sizes = sorted({c.vocab_size for c in report.cells})
    lines = [
        "",
        "Suggest correction - linear scan vs BK-tree",
        "=" * 44,
        f"{'algorithm':<12}" + "".join(f"{s:>12}" for s in sizes),
        "-" * (12 + 12 * len(sizes)),
    ]
    for algo in ("linear", "bktree"):
        row_cells = []
        for s in sizes:
            v = times.get((algo, s))
            row_cells.append(
                f"{v * 1000:>11.3f}m" if v is not None else f"{'-':>12}"
            )
        lines.append(f"{algo:<12}" + "".join(row_cells))
    lines.append("")
    lines.append(
        "Median milliseconds for one batch of N typo queries "
        "(N varies; see metadata). Lower is better."
    )
    lines.append(
        "See benchmarks/results/*.{json,csv,md} for raw data + memory."
    )
    return "\n".join(lines)


def render_markdown(report: SuggestBenchmarkReport) -> str:
    times = _by_metric(report.cells, "time_median_seconds")
    mem = _by_metric(report.cells, "memory_peak_bytes")
    sizes = sorted({c.vocab_size for c in report.cells})

    md: list[str] = []
    md.append("# Suggest Correction Benchmark - Linear vs BK-tree")
    md.append("")
    md.append("## Run metadata")
    md.append("")
    for k, v in report.metadata.items():
        md.append(f"- **{k}**: `{v}`")
    md.append("")
    md.append("## Median query batch time (ms)")
    md.append("")
    header = "| algorithm | " + " | ".join(f"n={s}" for s in sizes) + " |"
    sep = "|" + "|".join(["---"] * (1 + len(sizes))) + "|"
    md.append(header)
    md.append(sep)
    for algo in ("linear", "bktree"):
        row = [algo]
        for s in sizes:
            v = times.get((algo, s))
            row.append(f"{v * 1000:.3f}" if v is not None else "-")
        md.append("| " + " | ".join(row) + " |")
    md.append("")
    md.append("## Peak memory (KiB)")
    md.append("")
    md.append(header)
    md.append(sep)
    for algo in ("linear", "bktree"):
        row = [algo]
        for s in sizes:
            v = mem.get((algo, s))
            row.append(f"{v / 1024:.1f}" if v is not None else "-")
        md.append("| " + " | ".join(row) + " |")
    md.append("")
    return "\n".join(md)


def write_json(report: SuggestBenchmarkReport, path: Path) -> None:
    payload = {
        "metadata": report.metadata,
        "cells": [asdict(c) for c in report.cells],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(report: SuggestBenchmarkReport, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "algorithm", "vocab_size", "n_targets",
            "metric", "value", "unit", "n_samples",
        ])
        for c in report.cells:
            writer.writerow([
                c.algorithm, c.vocab_size, c.n_targets,
                c.metric, c.value, c.unit, c.n_samples,
            ])


def write_markdown(report: SuggestBenchmarkReport, path: Path) -> None:
    path.write_text(render_markdown(report), encoding="utf-8")


# --------------------------------------------------------------------- #
# Top-level orchestration                                               #
# --------------------------------------------------------------------- #


def collect_metadata(
    sizes: list[int], reps: int, n_targets: int, style: str
) -> dict:
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
        "vocab_sizes": sizes,
        "reps": reps,
        "n_targets_per_cell": n_targets,
        "max_distance": DEFAULT_MAX_DISTANCE,
        "vocab_style": style,
    }


def run(
    sizes: list[int],
    reps: int,
    n_targets: int,
    output_dir: Path,
    style: str = DEFAULT_STYLE,
    progress: Callable[[str], None] = print,
) -> SuggestBenchmarkReport:
    if style not in _VOCAB_GENERATORS:
        raise ValueError(
            f"unknown vocab style {style!r}; "
            f"choices: {sorted(_VOCAB_GENERATORS)}"
        )
    generator = _VOCAB_GENERATORS[style]

    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = collect_metadata(sizes, reps, n_targets, style)
    report = SuggestBenchmarkReport(metadata=metadata)

    for size in sizes:
        progress(f"Generating {size}-term {style} vocabulary...")
        vocab = generator(size)
        progress(f"Measuring n={size}...")
        report.cells.extend(measure(vocab, n_targets, reps))

    ts = metadata["run_timestamp_utc"].replace(":", "-")
    write_json(report, output_dir / f"suggest-benchmark-{ts}.json")
    write_csv(report, output_dir / f"suggest-benchmark-{ts}.csv")
    write_markdown(report, output_dir / f"suggest-benchmark-{ts}.md")

    progress(render_terminal(report))
    progress("")
    progress(f"Results written to {output_dir}/suggest-benchmark-{ts}.{{json,csv,md}}")
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
        prog="python -m benchmarks.run_suggest_benchmark",
        description="Benchmark suggest_corrections: linear vs BK-tree.",
    )
    parser.add_argument(
        "--sizes",
        type=_parse_sizes,
        default=list(DEFAULT_SIZES),
        help=f"Comma-separated vocabulary sizes (default: {','.join(map(str, DEFAULT_SIZES))})",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=DEFAULT_REPS,
        help=f"Measured repetitions per cell after one warmup (default: {DEFAULT_REPS})",
    )
    parser.add_argument(
        "--targets",
        type=int,
        default=DEFAULT_N_TARGETS,
        help=f"Typo targets per cell (default: {DEFAULT_N_TARGETS})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/results"),
        help="Directory for JSON/CSV/Markdown results",
    )
    parser.add_argument(
        "--style",
        choices=sorted(_VOCAB_GENERATORS),
        default=DEFAULT_STYLE,
        help=(
            f"Vocabulary generator (default: {DEFAULT_STYLE}). "
            "'clustered' models English morphology — best case for BK-tree. "
            "'random' is uniform random strings — worst case, documents the limit."
        ),
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=f"Fast mode: sizes={QUICK_SIZES}, reps={QUICK_REPS}, targets={QUICK_N_TARGETS}",
    )
    args = parser.parse_args(argv)

    if args.quick:
        args.sizes = list(QUICK_SIZES)
        args.reps = QUICK_REPS
        args.targets = QUICK_N_TARGETS

    run(
        sizes=args.sizes,
        reps=args.reps,
        n_targets=args.targets,
        output_dir=args.output,
        style=args.style,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
