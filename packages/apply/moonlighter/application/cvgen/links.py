"""The CV header's links, checked over HTTP by `moonlighter-apply doctor --online`.

2026-09-24: the templates linked a GitHub account that 404s, and every tailored
CV carried it to employers. The links live in the templates, not in
profile.yaml (moderncv's \\social[github]{user} builds the URL itself), so the
templates are what gets read. Offline by default: only the --online flag makes
network calls.
"""

import re
from typing import Any

import httpx
from moonlighter.application.cvgen.service import resolved_template_dir
from moonlighter.core.http_fetch import HEADERS

_TEMPLATE_NAMES = ("cv-template.en.tex", "cv-template.pt.tex")
_URL_COMMAND = re.compile(r"\\(?:httplink|href|homepage)(?:\[[^\]]*\])?\{([^}]+)\}")
_SOCIAL_COMMAND = re.compile(r"\\social\[(linkedin|github)\]\{([^}]+)\}")
_SOCIAL_URL = {
    "linkedin": "https://www.linkedin.com/in/{}",
    "github": "https://github.com/{}",
}
# LinkedIn answers every automated request with this status: it says nothing
# about whether the profile exists.
_BOT_WALL_STATUS = 999


def _strip_comment(line: str) -> str:
    """Drop a LaTeX comment, mid-line too. A % is escaped only by an odd run of
    backslashes: after a line break (two) it starts a comment."""
    for position, character in enumerate(line):
        if character != "%":
            continue
        backslashes = len(line[:position]) - len(line[:position].rstrip("\\"))
        if backslashes % 2 == 0:
            return line[:position]
    return line


def _is_marker(value: str) -> bool:
    """An unfilled template marker ({{LINKEDIN_USERNAME}}, %%BASE_SUMMARY%%). A
    lone % stays: "%20" is part of a real URL."""
    return "{" in value or "%%" in value


def template_links(text: str) -> list[str]:
    """Every header link a template renders, in order, each once. Commented-out
    lines and unfilled markers ({{LINKEDIN_USERNAME}}) are skipped."""
    links: list[str] = []
    for line in text.splitlines():
        line = _strip_comment(line)
        found = [
            (match.start(), _SOCIAL_URL[match[1]].format(match[2]))
            for match in _SOCIAL_COMMAND.finditer(line)
            if not _is_marker(match[2])
        ]
        found += [
            (match.start(), match[1] if "://" in match[1] else f"https://{match[1]}")
            for match in _URL_COMMAND.finditer(line)
            if not _is_marker(match[1])
        ]
        links.extend(url for _, url in sorted(found))
    return list(dict.fromkeys(links))


async def check_links(urls: list[str], client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """One entry per URL: the HTTP status and whether the link works. `ok` is
    None when the site refuses automated checks, so a person has to look."""
    report: list[dict[str, Any]] = []
    for url in urls:
        try:
            response = await client.get(url)
        except httpx.HTTPError as error:
            report.append({"url": url, "status": None, "ok": False, "note": str(error)})
            continue
        if response.status_code == _BOT_WALL_STATUS:
            note = "the site refuses automated checks — open it in a browser"
            report.append({"url": url, "status": response.status_code, "ok": None, "note": note})
            continue
        works = response.status_code < 400
        report.append({"url": url, "status": response.status_code, "ok": works, "note": None})
    return report


async def link_report(
    config: dict[str, Any], client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Check the header links of both CV templates in cv.template_dir."""
    directory = resolved_template_dir(config)
    urls: list[str] = []
    for name in _TEMPLATE_NAMES:
        path = directory / name
        if path.exists():
            urls.extend(template_links(path.read_text()))
    urls = list(dict.fromkeys(urls))
    if not urls:
        return []
    if client is not None:
        return await check_links(urls, client)
    async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=HEADERS) as owned:
        return await check_links(urls, owned)
