"""Checks the assembled docs site for what `zensical build --strict` does not see.

Measured 2026-09-23: --strict validates markdown links, but not `extra_css` files, and
the site is assembled by scripts/build_docs.sh from two per-language builds plus shared
assets. This checks that:
- the night-shift stylesheet exists in both language outputs;
- llms.txt is at the site root;
- every Pages URL a guide file references exists in the assembled site;
- every guide page produced an HTML page, and (with --require-dates) that page renders a
  revision date — proof the stamp ran and the dates reached the theme.

Usage:
    python scripts/check_built_site.py SITE GUIDE [--require-dates]
"""

import re
import sys
from pathlib import Path

SITE_URL = "https://albertosca.github.io/moonlighter/"
STYLESHEET = "stylesheets/night-shift.css"
_PAGES_URL = re.compile(re.escape(SITE_URL) + r"([^\s\"'()<>]*)")
_DATE_MARK = "md-source-file__fact"
_LANG_OUTPUT = {"en": Path(), "pt": Path("pt")}


def page_output(rel_md: Path) -> Path:
    if rel_md.name == "index.md":
        return rel_md.parent / "index.html"
    return rel_md.with_suffix("") / "index.html"


def _url_target(site: Path, rel: str) -> Path:
    target = site / rel.split("#", 1)[0]
    if rel == "" or rel.endswith("/") or target.is_dir():
        return target / "index.html"
    return target


def site_problems(site: Path, guide: Path, require_dates: bool) -> list[str]:
    problems: list[str] = []
    for lang_root in (site, site / "pt"):
        if not (lang_root / STYLESHEET).is_file():
            problems.append(f"missing {lang_root / STYLESHEET}")
    if not (site / "llms.txt").is_file():
        problems.append("missing llms.txt at the site root")
    sources = sorted([*guide.rglob("*.md"), *guide.rglob("*.txt")])
    for source in sources:
        for rel in _PAGES_URL.findall(source.read_text()):
            if not _url_target(site, rel).is_file():
                problems.append(f"{source}: {SITE_URL}{rel} is not in the built site")
    for lang, out_prefix in _LANG_OUTPUT.items():
        for md in sorted((guide / lang).rglob("*.md")):
            html = site / out_prefix / page_output(md.relative_to(guide / lang))
            if not html.is_file():
                problems.append(f"{md}: no built page at {html}")
            elif require_dates and _DATE_MARK not in html.read_text():
                problems.append(f"{html}: no revision date rendered")
    return problems


def main(argv: list[str]) -> int:
    site, guide = Path(argv[1]), Path(argv[2])
    problems = site_problems(site, guide, require_dates="--require-dates" in argv[3:])
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("Built site OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
