"""Generate HTML API documentation from the ``src/`` docstrings.

Thin wrapper around ``pdoc`` that fixes the output directory and
the input package list, so contributors do not have to remember the
exact flags. Run from the repository root:

.. code-block:: console

    python scripts/build_api_docs.py

The result lands in ``docs/api/`` (gitignored). Open
``docs/api/index.html`` in a browser to view the full surface.

CI uses :func:`build_to_temp` to verify that every public symbol's
docstring parses cleanly — the generated files themselves are not
checked in.

References:
* `pdoc documentation <https://pdoc.dev/docs/pdoc.html>`_ for the
  underlying tool and its docstring conventions.
* :doc:`/CONTRIBUTING.md` §3.3 for the docstring style this project
  follows.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "api"
PACKAGES = ("src",)


def build_to(output_dir: Path) -> None:
    """Run ``pdoc`` writing HTML into ``output_dir``.

    Re-raises :class:`subprocess.CalledProcessError` on failure so a
    CI step that wraps this function fails the build when any
    docstring fails to parse. ``pdoc`` exits non-zero on syntax
    errors in module docstrings or on missing optional dependencies
    inside imported modules.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pdoc",
        *PACKAGES,
        "--output-directory",
        str(output_dir),
    ]
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)


def build_to_temp() -> None:
    """Build into a discarded temp directory; for CI smoke checks.

    The generated HTML is thrown away — we only care that pdoc did
    not raise. If a contributor adds a malformed docstring, this
    function surfaces it on CI before the change can land on main.
    """
    with tempfile.TemporaryDirectory(prefix="pdoc-smoke-") as tmp:
        build_to(Path(tmp))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/build_api_docs.py",
        description="Generate API HTML docs from src/ docstrings.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the output directory before building (avoids stale pages)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Build into a temp directory and discard — for CI verification",
    )
    args = parser.parse_args(argv)

    if args.smoke:
        build_to_temp()
        print("pdoc smoke build succeeded; docstrings parse cleanly.")
        return 0

    if args.clean and args.output.exists():
        shutil.rmtree(args.output)

    build_to(args.output)
    print(f"API docs written to {args.output}")
    print(f"Open {args.output / 'index.html'} in a browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
