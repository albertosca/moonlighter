"""EN/PT structural parity for guide/: the same pages and the same H2/H3 sequence in each pair.

The pages are the relative .md paths under guide/en and guide/pt. The check is structural only: it cannot tell whether a page is actually translated, only that neither language has grown sections the other lacks.

Usage:
    python scripts/check_docs_parity.py [guide_root]
"""

import re
import sys
from pathlib import Path

from markdown_lines import lines_outside_fences

_HEADING = re.compile(r"^(#{2,3})\s+\S")


def heading_levels(text: str) -> list[int]:
    """H2/H3 levels in document order, ignoring fenced code blocks."""
    matches = (_HEADING.match(line) for line in lines_outside_fences(text))
    return [len(match.group(1)) for match in matches if match]


def _pages(language_root: Path) -> set[str]:
    return {page.relative_to(language_root).as_posix() for page in language_root.rglob("*.md")}


def _sequence_problems(guide_root: Path, shared_pages: set[str]) -> list[str]:
    problems: list[str] = []
    for relative in sorted(shared_pages):
        english_levels = heading_levels((guide_root / "en" / relative).read_text())
        portuguese_levels = heading_levels((guide_root / "pt" / relative).read_text())
        if english_levels != portuguese_levels:
            problems.append(
                f"{relative}: en H2/H3 sequence {english_levels} != pt {portuguese_levels}"
            )
    return problems


def parity_problems(guide_root: Path) -> list[str]:
    english_pages = _pages(guide_root / "en")
    portuguese_pages = _pages(guide_root / "pt")
    if not english_pages:
        return [f"no pages under {guide_root / 'en'}"]
    problems = [
        f"missing in pt: {relative}" for relative in sorted(english_pages - portuguese_pages)
    ]
    problems += [
        f"missing in en: {relative}" for relative in sorted(portuguese_pages - english_pages)
    ]
    return problems + _sequence_problems(guide_root, english_pages & portuguese_pages)


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "guide"
    problems = parity_problems(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("EN/PT parity OK (structure only — not a translation check).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
