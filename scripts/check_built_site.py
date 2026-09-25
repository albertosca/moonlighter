"""Checks the assembled docs site for what `zensical build --strict` does not see.

Measured 2026-09-23: --strict validates markdown links, but not `extra_css` files, and
the site is assembled by scripts/build_docs.sh from two per-language builds plus shared
assets. This checks that:
- the night-shift stylesheet exists in both language outputs;
- llms.txt is at the site root;
- every Pages URL a guide file or README references exists in the assembled site, and a
  URL's #fragment names an id on the target page (a renamed heading would otherwise
  dead-link the README with the build green); the READMEs are the root README.md and
  README.pt.md plus packages/*/README*.md, the repository root being GUIDE's parent;
- every guide page produced an HTML page, and (with --require-dates) that page renders a
  revision date — proof the stamp ran and the dates reached the theme;
- every such page carries absolute hreflang links to itself in both languages plus
  x-default (the theme's own links named each language's home, relatively, which Google
  discards).

Usage:
    python scripts/check_built_site.py SITE GUIDE [--require-dates]
"""

import re
import sys
from pathlib import Path

SITE_URL = "https://albertosca.github.io/moonlighter/"
STYLESHEET = "stylesheets/night-shift.css"
_PAGES_URL = re.compile(re.escape(SITE_URL) + r"([^\s\"'()<>]*)")
# A bare URL that ends a sentence: the punctuation belongs to the prose, not the URL.
_TRAILING_PUNCTUATION = ".,;:!?"
_DATE_MARK = "md-source-file__fact"
_LANG_OUTPUT = {"en": Path(), "pt": Path("pt")}
_ALTERNATE_LINK = re.compile(r"<link\b[^>]*\brel=\"alternate\"[^>]*>")
_ATTRIBUTE = re.compile(r'(\w[\w-]*)="([^"]*)"')


def page_output(rel_md: Path) -> Path:
    if rel_md.name == "index.md":
        return rel_md.parent / "index.html"
    return rel_md.with_suffix("") / "index.html"


def _url_target(site: Path, rel: str) -> Path:
    target = site / rel.split("#", 1)[0]
    if rel == "" or rel.endswith("/") or target.is_dir():
        return target / "index.html"
    return target


def pages_urls(text: str) -> list[str]:
    return [rel.rstrip(_TRAILING_PUNCTUATION) for rel in _PAGES_URL.findall(text)]


def _readmes(root: Path) -> list[Path]:
    found = [root / "README.md", root / "README.pt.md", *root.glob("packages/*/README*.md")]
    return sorted(path for path in found if path.is_file())


def _url_problem(source: Path, site: Path, rel: str) -> str | None:
    target = _url_target(site, rel)
    if not target.is_file():
        return f"{source}: {SITE_URL}{rel} is not in the built site"
    fragment = rel.partition("#")[2]
    if fragment and f'id="{fragment}"' not in target.read_text():
        return f'{source}: {SITE_URL}{rel} has no id="{fragment}" in {target}'
    return None


def expected_alternates(page_path: str) -> dict[str, str]:
    return {
        "en": f"{SITE_URL}{page_path}",
        "pt": f"{SITE_URL}pt/{page_path}",
        "x-default": f"{SITE_URL}{page_path}",
    }


def page_alternates(html: str) -> list[tuple[str, str]]:
    """Every (hreflang, href) pair, duplicates kept: a stray second link for one
    language must not hide behind the right one."""
    alternates: list[tuple[str, str]] = []
    for link in _ALTERNATE_LINK.findall(html):
        attributes = dict(_ATTRIBUTE.findall(link))
        if "hreflang" in attributes:
            alternates.append((attributes["hreflang"], attributes.get("href", "")))
    return sorted(alternates)


def site_problems(site: Path, guide: Path, require_dates: bool) -> list[str]:
    problems: list[str] = []
    for lang_root in (site, site / "pt"):
        if not (lang_root / STYLESHEET).is_file():
            problems.append(f"missing {lang_root / STYLESHEET}")
    if not (site / "llms.txt").is_file():
        problems.append("missing llms.txt at the site root")
    sources = sorted([*guide.rglob("*.md"), *guide.rglob("*.txt")]) + _readmes(guide.parent)
    for source in sources:
        for rel in pages_urls(source.read_text()):
            problem = _url_problem(source, site, rel)
            if problem:
                problems.append(problem)
    for lang, out_prefix in _LANG_OUTPUT.items():
        for md in sorted((guide / lang).rglob("*.md")):
            html = site / out_prefix / page_output(md.relative_to(guide / lang))
            if not html.is_file():
                problems.append(f"{md}: no built page at {html}")
                continue
            page_html = html.read_text()
            if require_dates and _DATE_MARK not in page_html:
                problems.append(f"{html}: no revision date rendered")
            page_path = page_output(md.relative_to(guide / lang)).parent.as_posix()
            page_path = "" if page_path == "." else f"{page_path}/"
            expected = sorted(expected_alternates(page_path).items())
            if page_alternates(page_html) != expected:
                problems.append(
                    f"{html}: hreflang links {page_alternates(page_html)} != {expected}"
                )
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
