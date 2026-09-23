"""Writes each guide page's last-commit date into its `revision_date` frontmatter,
which the Zensical theme renders as the page's "last updated" date. Runs on the CI
working copy only — the stamped files are never committed.

Refuses a shallow clone: measured 2026-09-23, in a `--depth 1` checkout every file's
`git log -1` answers the newest commit, so every page would silently claim the same
date. The docs workflow checks out with `fetch-depth: 0`.

Usage:
    python scripts/stamp_revision_dates.py guide
"""

import re
import subprocess
import sys
from pathlib import Path

_FRONTMATTER = re.compile(r"\A---\n(?P<body>.*?)^---\n", re.DOTALL | re.MULTILINE)
_KEY = re.compile(r"^revision_date:.*$", re.MULTILINE)


class StampError(Exception):
    """A condition under which stamping would write wrong dates."""


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603 - literal argv, git on PATH
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,  # noqa: S607 - literal argv, git on PATH
    )
    return result.stdout.strip()


def ensure_full_history(repo: Path) -> None:
    if _git(repo, "rev-parse", "--is-shallow-repository") == "true":
        raise StampError(
            "shallow clone — every page would get the newest commit's date; check out with fetch-depth: 0"
        )


def last_commit_date(repo: Path, path: Path) -> str:
    date = _git(repo, "log", "-1", "--format=%cs", "--", str(path))
    if not date:
        raise StampError(f"{path} has no commit — commit it before building the site")
    return date


def with_revision_date(text: str, date: str) -> str:
    line = f"revision_date: {date}"
    match = _FRONTMATTER.match(text)
    if match is None:
        return f"---\n{line}\n---\n{text}"
    body = match.group("body")
    body = _KEY.sub(line, body) if _KEY.search(body) else f"{body}{line}\n"
    return f"---\n{body}---\n{text[match.end() :]}"


def stamp(guide_root: Path) -> int:
    repo = Path(_git(guide_root, "rev-parse", "--show-toplevel"))
    ensure_full_history(repo)
    pages = sorted(guide_root.rglob("*.md"))
    dates = {page: last_commit_date(repo, page.resolve()) for page in pages}
    for page, date in dates.items():
        page.write_text(with_revision_date(page.read_text(), date))
    return len(pages)


def main(argv: list[str]) -> int:
    try:
        count = stamp(Path(argv[1]))
    except StampError as error:
        print(f"stamp_revision_dates: {error}", file=sys.stderr)
        return 1
    print(f"Stamped {count} pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
