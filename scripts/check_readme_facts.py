"""Keeps the proof numbers on the READMEs, the site home and llms.txt true, and the
READMEs' relative links alive.

Facts live between `<!-- facts -->` and `<!-- /facts -->`. Rules:
- tests: the written "N+" must not exceed the real count (a false claim) and must not
  trail it by more than STALE_BAND (stale). Real count = JUnit `tests` minus `skipped`,
  read from the report the test job already writes — a second --collect-only pass costs
  35-56 s and, without --no-cov, prints a false coverage FAIL (measured 2026-09-23).
- coverage: the written percentage must equal --cov-fail-under in pyproject.toml.
- packages: the written count must equal the number of packages/*/pyproject.toml.
Every file in FACT_FILES must hold exactly one block — a missing block must not pass.

Usage:
    python scripts/check_readme_facts.py --junit test-report.xml [--repo PATH]
"""

import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

FACT_FILES = (
    "README.md",
    "README.pt.md",
    "guide/en/index.md",
    "guide/pt/index.md",
    "guide/en/llms.txt",
)
LINK_FILES = ("README.md", "README.pt.md")
STALE_BAND = 200

_BLOCK = re.compile(r"<!-- facts -->(.*?)<!-- /facts -->", re.DOTALL)
_TESTS = re.compile(r"(\d[\d.,]*)\+\s*(?:tests|testes)")
_COVERAGE = re.compile(r"(\d+)%")
_PACKAGES = re.compile(r"(\d+)\s*(?:packages|pacotes)")
_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_MD_LINK = re.compile(r"\]\(([^)\s]+)")
_HTML_REF = re.compile(r"(?:src|srcset|href)=\"([^\"\s]+)")


@dataclass(frozen=True)
class Facts:
    tests: int
    coverage: int
    packages: int


def junit_test_count(junit: Path) -> int:
    root = ET.parse(junit).getroot()  # noqa: S314 - locally generated JUnit report
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return sum(int(s.get("tests", "0")) - int(s.get("skipped", "0")) for s in suites)


def real_facts(repo: Path, junit: Path) -> Facts:
    addopts = tomllib.loads((repo / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"][
        "addopts"
    ]
    gate = re.search(r"--cov-fail-under=(\d+)", addopts)
    if gate is None:
        raise ValueError("pyproject.toml addopts has no --cov-fail-under")
    packages = len(list((repo / "packages").glob("*/pyproject.toml")))
    return Facts(tests=junit_test_count(junit), coverage=int(gate.group(1)), packages=packages)


def _number(raw: str) -> int:
    return int(re.sub(r"[.,]", "", raw))


def fact_problems(name: str, text: str, real: Facts) -> list[str]:
    blocks = _BLOCK.findall(text)
    if len(blocks) != 1:
        return [f"{name}: expected exactly one facts block, found {len(blocks)}"]
    block = blocks[0]
    problems: list[str] = []
    tests = _TESTS.search(block)
    if tests is None:
        problems.append(f'{name}: facts block has no test count ("N+ tests")')
    else:
        claimed = _number(tests.group(1))
        if claimed > real.tests:
            problems.append(
                f"{name}: claims {claimed}+ tests but there are {real.tests} — a false claim"
            )
        elif real.tests - claimed > STALE_BAND:
            problems.append(
                f"{name}: claims {claimed}+ tests, real {real.tests} — stale by more than {STALE_BAND}"
            )
    coverage = _COVERAGE.search(block)
    if coverage is None or int(coverage.group(1)) != real.coverage:
        problems.append(f"{name}: coverage must read {real.coverage}% (the CI gate)")
    packages = _PACKAGES.search(block)
    if packages is None or int(packages.group(1)) != real.packages:
        problems.append(f"{name}: package count must read {real.packages}")
    return problems


def slug(heading: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    seen: dict[str, int] = {}
    result: set[str] = set()
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else _HEADING.match(line)
        if match is None:
            continue
        base = slug(match.group(1))
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


def link_problems(repo: Path, rel_file: str) -> list[str]:
    source = repo / rel_file
    text = source.read_text()
    problems: list[str] = []
    for target in [*_MD_LINK.findall(text), *_HTML_REF.findall(text)]:
        if re.match(r"^[a-z]+:", target):
            continue
        path_part, _, anchor = target.partition("#")
        dest = source if path_part == "" else (source.parent / path_part)
        if not dest.exists():
            problems.append(f"{rel_file}: {target} does not exist")
        elif anchor and dest.suffix == ".md" and anchor not in anchors(dest.read_text()):
            problems.append(f"{rel_file}: {target} — no such anchor")
    return problems


def main(argv: list[str]) -> int:
    args = dict(zip(argv[1::2], argv[2::2], strict=False))
    repo = Path(args.get("--repo", Path(__file__).resolve().parents[1]))
    real = real_facts(repo, Path(args["--junit"]))
    problems: list[str] = []
    for name in FACT_FILES:
        problems += fact_problems(name, (repo / name).read_text(), real)
    for name in LINK_FILES:
        problems += link_problems(repo, name)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(
        f"README facts and links OK ({real.tests} tests, {real.coverage}% gate, {real.packages} packages)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
