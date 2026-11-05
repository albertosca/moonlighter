"""Fail when a Python file grows past the repository's length limit.

A long file is a module doing more than one thing. The policy lives in the
root pyproject.toml under [tool.moonlighter.file-length]: `limit` is the
length every file must fit; a file may exceed it only when the `justified`
table names it with a reason; nothing may exceed `ceiling`. A justification
for a file that no longer needs it is reported too, so the list cannot rot.

Usage:
    python scripts/check_file_length.py [PATH ...]

With no PATH, every .py file under packages/, tests/ and scripts/ is checked.
A PATH that selects no .py file (missing, not Python, a directory without Python
files, or outside the repository) fails the run.
"""

import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_ROOTS = (Path("packages"), Path("tests"), Path("scripts"))
_NEVER_MEASURED = frozenset({".venv", "__pycache__"})


@dataclass(frozen=True)
class LengthPolicy:
    """The limits read from pyproject.toml; `justified` maps a path to its reason."""

    limit: int
    ceiling: int
    justified: Mapping[str, str]


def load_policy(repo_root: Path) -> LengthPolicy:
    """Read [tool.moonlighter.file-length] from the root pyproject.toml."""
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text())
    table = pyproject["tool"]["moonlighter"]["file-length"]
    return LengthPolicy(table["limit"], table["ceiling"], table.get("justified", {}))


def _python_files(repo_root: Path, roots: Iterable[Path]) -> list[Path]:
    """Every measured .py file under the roots, as paths relative to the repo."""
    found: set[Path] = set()
    for root in roots:
        absolute_root = repo_root / root
        candidates = [absolute_root] if absolute_root.is_file() else absolute_root.rglob("*.py")
        found.update(
            candidate.relative_to(repo_root)
            for candidate in candidates
            if not _NEVER_MEASURED.intersection(candidate.parts)
        )
    return sorted(found)


def _line_count(path: Path) -> int:
    return len(path.read_text().splitlines())


def _length_violation(path: str, lines: int, policy: LengthPolicy) -> str | None:
    if lines > policy.ceiling:
        return (
            f"{path} has {lines} lines; nothing may exceed the ceiling"
            f" of {policy.ceiling}, justified or not"
        )
    if lines > policy.limit and path not in policy.justified:
        return (
            f"{path} has {lines} lines; the limit is {policy.limit}"
            " (justify it in pyproject.toml or split it)"
        )
    return None


def _justification_violation(
    repo_root: Path, path: str, *, reason: str, policy: LengthPolicy
) -> str | None:
    if not (repo_root / path).is_file():
        return f"{path} is justified in pyproject.toml but does not exist; delete the entry"
    lines = _line_count(repo_root / path)
    if lines <= policy.limit:
        return f"{path} is justified in pyproject.toml but has {lines} lines; delete the entry"
    if not reason.strip():
        return f"{path} is justified with an empty reason in pyproject.toml"
    return None


def _is_under(path: str, roots: Iterable[Path]) -> bool:
    return any(Path(path).is_relative_to(root) for root in roots)


def check(repo_root: Path, roots: Sequence[Path] = _DEFAULT_ROOTS) -> list[str]:
    """Every violation under the roots, as one-line messages; [] when all fit."""
    policy = load_policy(repo_root)
    length_violations = (
        _length_violation(path.as_posix(), _line_count(repo_root / path), policy)
        for path in _python_files(repo_root, roots)
    )
    justification_violations = (
        _justification_violation(repo_root, path, reason=reason, policy=policy)
        for path, reason in policy.justified.items()
        if _is_under(path, roots)
    )
    return [
        violation
        for violation in (*length_violations, *justification_violations)
        if violation is not None
    ]


def _selected_root(repo_root: Path, argument: str) -> Path | None:
    """The argument as a repo-relative root, or None when it selects no measured .py file.

    Both sides are resolved first: a macOS temporary directory sits behind /var -> /private/var, and a path outside the repository must be refused rather than raise in relative_to.
    """
    resolved = (repo_root / argument).resolve()
    repository = repo_root.resolve()
    if not resolved.is_relative_to(repository):
        return None
    if resolved.is_file() and resolved.suffix != ".py":
        return None
    relative = resolved.relative_to(repository)
    return relative if _python_files(repo_root, [relative]) else None


def main(repo_root: Path, arguments: Sequence[str]) -> int:
    """Print the verdict; exit status 1 when any violation was found.

    With explicit arguments, one that selects no .py file is a failure of its own and never falls back to the default roots.
    """
    selected = [(argument, _selected_root(repo_root, argument)) for argument in arguments]
    rejected = [f"{argument}: selects no .py file" for argument, root in selected if root is None]
    roots = [root for _, root in selected if root is not None]
    violations = check(repo_root, roots if arguments else _DEFAULT_ROOTS)
    if not rejected and not violations:
        print(f"Every Python file is within {load_policy(repo_root).limit} lines.")
        return 0
    print("File length gate failed:")
    for line in (*rejected, *violations):
        print(f"  - {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main(Path(__file__).resolve().parent.parent, sys.argv[1:]))
