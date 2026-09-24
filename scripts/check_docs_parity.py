"""EN/PT structural parity for guide/: the same relative .md paths under guide/en and
guide/pt, and the same H2/H3 sequence in each pair.

Structural only: it cannot tell whether a page is actually translated, only that
neither language has grown sections the other lacks.

Usage:
    python scripts/check_docs_parity.py [guide_root]
"""

import re
import sys
from pathlib import Path

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{2,3})\s+\S")


def heading_levels(text: str) -> list[int]:
    """H2/H3 levels in document order, ignoring fenced code blocks."""
    levels: list[int] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            levels.append(len(match.group(1)))
    return levels


def parity_problems(guide_root: Path) -> list[str]:
    en, pt = guide_root / "en", guide_root / "pt"
    en_pages = {p.relative_to(en).as_posix() for p in en.rglob("*.md")}
    pt_pages = {p.relative_to(pt).as_posix() for p in pt.rglob("*.md")}
    if not en_pages:
        return [f"no pages under {en}"]
    problems = [f"missing in pt: {rel}" for rel in sorted(en_pages - pt_pages)]
    problems += [f"missing in en: {rel}" for rel in sorted(pt_pages - en_pages)]
    for rel in sorted(en_pages & pt_pages):
        en_levels = heading_levels((en / rel).read_text())
        pt_levels = heading_levels((pt / rel).read_text())
        if en_levels != pt_levels:
            problems.append(f"{rel}: en H2/H3 sequence {en_levels} != pt {pt_levels}")
    return problems


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
