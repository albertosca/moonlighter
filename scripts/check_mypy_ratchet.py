"""Fail when mypy over tests/ finds more errors in a file than the baseline allows.

tests/ runs under the rest of strict without the annotation rules (see the
`tests.*` override in pyproject.toml). The errors that remained when the gate
was added live in scripts/mypy_tests_baseline.json, one count per file. A file
may only go down: more errors than its count fails, and so does fewer, until
`--update` locks the gain in, so the baseline cannot rot above the real number.

Usage:
    python scripts/check_mypy_ratchet.py [--update]

A mypy crash, or output this script cannot reconcile with mypy's own
"Found N errors" summary, fails the run instead of reading as zero errors.
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

_BASELINE = Path(__file__).resolve().parent / "mypy_tests_baseline.json"
_ERROR_LINE = re.compile(r"^(?P<path>[^:\s]+\.py):\d+: error: ", re.MULTILINE)
_SUMMARY = re.compile(r"^Found (?P<total>\d+) errors? in \d+ files?", re.MULTILINE)


class RatchetError(RuntimeError):
    """mypy did not produce output the ratchet can trust."""


def run_mypy() -> subprocess.CompletedProcess[str]:
    """Run mypy over tests/, with scripts/ importable the way pytest's pythonpath makes it."""
    environment = {**os.environ, "MYPYPATH": "scripts"}
    return subprocess.run(
        [sys.executable, "-m", "mypy", "tests"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def count_errors(result: subprocess.CompletedProcess[str]) -> dict[str, int]:
    """Errors per file. Raises RatchetError when the run cannot be read as a count."""
    if result.returncode not in {0, 1}:
        message = f"mypy exited with code {result.returncode}: {result.stderr.strip()[:500]}"
        raise RatchetError(message)
    counts = Counter(match["path"] for match in _ERROR_LINE.finditer(result.stdout))
    if result.returncode == 0:
        return dict(counts)
    summary = _SUMMARY.search(result.stdout)
    if summary is None:
        raise RatchetError("mypy reported errors but printed no summary line")
    total = int(summary["total"])
    if counts.total() != total:
        raise RatchetError(f"parsed {counts.total()} of the {total} errors mypy reported")
    return dict(counts)


def violations(counts: Mapping[str, int], baseline: Mapping[str, int]) -> list[str]:
    """Every file above its allowance, then every file below it (the baseline is stale)."""
    above = [
        f"{path} has {count} mypy errors; the baseline allows {baseline.get(path, 0)}"
        " — fix the new ones"
        for path, count in sorted(counts.items())
        if count > baseline.get(path, 0)
    ]
    below = [
        f"{path} has {counts.get(path, 0)} mypy errors, below the baseline's {allowed}"
        " — run with --update to lock it in"
        for path, allowed in sorted(baseline.items())
        if counts.get(path, 0) < allowed
    ]
    return above + below


def main(arguments: Sequence[str], *, baseline_path: Path = _BASELINE) -> int:
    try:
        counts = count_errors(run_mypy())
    except RatchetError as error:
        print(error)
        return 1
    if "--update" in arguments:
        baseline_path.write_text(json.dumps(dict(sorted(counts.items())), indent=2) + "\n")
        print(f"baseline: {sum(counts.values())} errors in {len(counts)} files")
        return 0
    problems = violations(counts, json.loads(baseline_path.read_text()))
    for problem in problems:
        print(problem)
    if not problems:
        print(f"mypy over tests/: {sum(counts.values())} errors, none above the baseline")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
