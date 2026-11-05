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
  discards), and a sitemap.xml beside it (the theme's language switcher fetches one next
  to every hreflang URL; build_docs.sh copies it there).

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


def page_output(relative_markdown: Path) -> Path:
    if relative_markdown.name == "index.md":
        return relative_markdown.parent / "index.html"
    return relative_markdown.with_suffix("") / "index.html"


def _url_target(site: Path, relative_url: str) -> Path:
    target = site / relative_url.split("#", 1)[0]
    if relative_url == "" or relative_url.endswith("/") or target.is_dir():
        return target / "index.html"
    return target


def pages_urls(text: str) -> list[str]:
    return [url.rstrip(_TRAILING_PUNCTUATION) for url in _PAGES_URL.findall(text)]


def _readmes(root: Path) -> list[Path]:
    found = [root / "README.md", root / "README.pt.md", *root.glob("packages/*/README*.md")]
    return sorted(path for path in found if path.is_file())


def _url_problem(source: Path, site: Path, relative_url: str) -> str | None:
    target = _url_target(site, relative_url)
    if not target.is_file():
        return f"{source}: {SITE_URL}{relative_url} is not in the built site"
    fragment = relative_url.partition("#")[2]
    if fragment and f'id="{fragment}"' not in target.read_text():
        return f'{source}: {SITE_URL}{relative_url} has no id="{fragment}" in {target}'
    return None


def expected_alternates(page_path: str) -> dict[str, str]:
    return {
        "en": f"{SITE_URL}{page_path}",
        "pt": f"{SITE_URL}pt/{page_path}",
        "x-default": f"{SITE_URL}{page_path}",
    }


def page_alternates(html: str) -> list[tuple[str, str]]:
    """Every (hreflang, href) pair, sorted, with duplicates kept.

    A stray second link for one language must not hide behind the right one.
    """
    alternates: list[tuple[str, str]] = []
    for link in _ALTERNATE_LINK.findall(html):
        attributes = dict(_ATTRIBUTE.findall(link))
        if "hreflang" in attributes:
            alternates.append((attributes["hreflang"], attributes.get("href", "")))
    return sorted(alternates)


def _asset_problems(site: Path) -> list[str]:
    stylesheets = [root / STYLESHEET for root in (site, site / "pt")]
    problems = [f"missing {stylesheet}" for stylesheet in stylesheets if not stylesheet.is_file()]
    if not (site / "llms.txt").is_file():
        problems.append("missing llms.txt at the site root")
    return problems


def _url_problems(site: Path, guide: Path) -> list[str]:
    sources = sorted([*guide.rglob("*.md"), *guide.rglob("*.txt")]) + _readmes(guide.parent)
    checked = (
        _url_problem(source, site, relative_url)
        for source in sources
        for relative_url in pages_urls(source.read_text())
    )
    return [problem for problem in checked if problem]


def _hreflang_problems(html: Path, page_html: str, relative_html: Path) -> list[str]:
    page_path = relative_html.parent.as_posix()
    page_path = "" if page_path == "." else f"{page_path}/"
    expected = sorted(expected_alternates(page_path).items())
    found = page_alternates(page_html)
    if found != expected:
        return [f"{html}: hreflang links {found} != {expected}"]
    return []


def _page_problems(
    language_site: Path, language_guide: Path, markdown: Path, *, require_dates: bool
) -> list[str]:
    relative_html = page_output(markdown.relative_to(language_guide))
    html = language_site / relative_html
    if not html.is_file():
        return [f"{markdown}: no built page at {html}"]
    page_html = html.read_text()
    problems: list[str] = []
    if require_dates and _DATE_MARK not in page_html:
        problems.append(f"{html}: no revision date rendered")
    if not (html.parent / "sitemap.xml").is_file():
        problems.append(f"{html.parent}: no sitemap.xml copy for the language switcher")
    return problems + _hreflang_problems(html, page_html, relative_html)


def site_problems(site: Path, guide: Path, *, require_dates: bool) -> list[str]:
    problems = _asset_problems(site) + _url_problems(site, guide)
    for language, output_prefix in _LANG_OUTPUT.items():
        language_guide = guide / language
        for markdown in sorted(language_guide.rglob("*.md")):
            problems += _page_problems(
                site / output_prefix, language_guide, markdown, require_dates=require_dates
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
