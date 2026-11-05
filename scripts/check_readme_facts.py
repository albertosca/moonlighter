"""Keeps the proof numbers in the READMEs, the site home, llms.txt and the social preview true.

It also keeps the READMEs' relative links alive.

Facts live between `<!-- facts -->` and `<!-- /facts -->`. Rules:
- tests: the written "N+" must not exceed the real count (a false claim) and must not
  trail it by more than STALE_BAND (stale). Real count = JUnit `tests` minus `skipped`,
  read from the report the test job already writes. A second --collect-only pass costs
  35-56 s and, without --no-cov, prints a false coverage FAIL (measured 2026-09-23).
- coverage: the written percentage must equal --cov-fail-under in pyproject.toml.
- packages: the written count must equal the number of packages/*/pyproject.toml.
- "branch" and "mypy strict", when claimed, must match [tool.coverage.run] branch and
  [tool.mypy] strict in pyproject.toml.
Every file in FACT_FILES must hold exactly one block, so a missing block cannot pass.

Usage:
    python scripts/check_readme_facts.py --junit test-report.xml [--repo PATH]
"""

import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from readme_links import link_problems

FACT_FILES = (
    "README.md",
    "README.pt.md",
    "guide/en/index.md",
    "guide/pt/index.md",
    "guide/en/llms.txt",
    "assets/site/social-preview.svg",
)
LINK_FILES = ("README.md", "README.pt.md")
STALE_BAND = 200

_BLOCK = re.compile(r"<!-- facts -->(.*?)<!-- /facts -->", re.DOTALL)
_TESTS = re.compile(r"(\d[\d.,]*)\+\s*(?:tests|testes)")
_COVERAGE = re.compile(r"(\d+)%")
_PACKAGES = re.compile(r"(\d+)\s*(?:packages|pacotes)")
_BRANCH_CLAIM = re.compile(r"\bbranch(?:es)?\b", re.IGNORECASE)
_MYPY_STRICT_CLAIM = re.compile(r"\bmypy strict\b", re.IGNORECASE)


@dataclass(frozen=True)
class Facts:
    tests: int
    coverage: int
    packages: int
    branch_coverage: bool
    mypy_strict: bool


def junit_test_count(junit: Path) -> int:
    root = ET.parse(junit).getroot()  # noqa: S314 - locally generated JUnit report
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return sum(int(suite.get("tests", "0")) - int(suite.get("skipped", "0")) for suite in suites)


def real_facts(repo: Path, junit: Path) -> Facts:
    tool = tomllib.loads((repo / "pyproject.toml").read_text())["tool"]
    addopts = tool["pytest"]["ini_options"]["addopts"]
    gate = re.search(r"--cov-fail-under=(\d+)", addopts)
    if gate is None:
        raise ValueError("pyproject.toml addopts has no --cov-fail-under")
    packages = len(list((repo / "packages").glob("*/pyproject.toml")))
    return Facts(
        tests=junit_test_count(junit),
        coverage=int(gate.group(1)),
        packages=packages,
        branch_coverage=tool.get("coverage", {}).get("run", {}).get("branch", False) is True,
        mypy_strict=tool.get("mypy", {}).get("strict", False) is True,
    )


def _number(raw: str) -> int:
    return int(re.sub(r"[.,]", "", raw))


def _test_count_problems(name: str, block: str, real: Facts) -> list[str]:
    tests = _TESTS.search(block)
    if tests is None:
        return [f'{name}: facts block has no test count ("N+ tests")']
    claimed = _number(tests.group(1))
    if claimed > real.tests:
        return [f"{name}: claims {claimed}+ tests but there are {real.tests} — a false claim"]
    if real.tests - claimed > STALE_BAND:
        return [
            f"{name}: claims {claimed}+ tests, real {real.tests} — stale by more than {STALE_BAND}"
        ]
    return []


def _gate_and_package_problems(name: str, block: str, real: Facts) -> list[str]:
    problems: list[str] = []
    coverage = _COVERAGE.search(block)
    if coverage is None or int(coverage.group(1)) != real.coverage:
        problems.append(f"{name}: coverage must read {real.coverage}% (the CI gate)")
    packages = _PACKAGES.search(block)
    if packages is None or int(packages.group(1)) != real.packages:
        problems.append(f"{name}: package count must read {real.packages}")
    return problems


def _claim_problems(name: str, block: str, real: Facts) -> list[str]:
    problems: list[str] = []
    if _BRANCH_CLAIM.search(block) and not real.branch_coverage:
        problems.append(f"{name}: claims branch coverage but [tool.coverage.run] branch is off")
    if _MYPY_STRICT_CLAIM.search(block) and not real.mypy_strict:
        problems.append(f"{name}: claims mypy strict but [tool.mypy] strict is off")
    return problems


def fact_problems(name: str, text: str, real: Facts) -> list[str]:
    blocks = _BLOCK.findall(text)
    if len(blocks) != 1:
        return [f"{name}: expected exactly one facts block, found {len(blocks)}"]
    block = blocks[0]
    return [
        *_test_count_problems(name, block, real),
        *_gate_and_package_problems(name, block, real),
        *_claim_problems(name, block, real),
    ]


def _all_problems(repo: Path, real: Facts) -> list[str]:
    problems: list[str] = []
    for name in FACT_FILES:
        problems += fact_problems(name, (repo / name).read_text(), real)
    for name in LINK_FILES:
        problems += link_problems(repo, name)
    return problems


def main(argv: list[str]) -> int:
    flags = dict(zip(argv[1::2], argv[2::2], strict=False))
    repo = Path(flags.get("--repo", Path(__file__).resolve().parents[1]))
    real = real_facts(repo, Path(flags["--junit"]))
    problems = _all_problems(repo, real)
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
