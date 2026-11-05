"""Checks that every relative link in a markdown file points at a file, and an anchor, that exists."""

import re
from pathlib import Path

from markdown_lines import lines_outside_fences

_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_MD_LINK = re.compile(r"\]\(([^)\s]+)")
_HTML_REF = re.compile(r"(?:src|srcset|href)=\"([^\"\s]+)")
_ABSOLUTE_URL = re.compile(r"^[a-z]+:")


def slug(heading: str) -> str:
    """The anchor GitHub gives a heading: links unwrapped, lower-cased, punctuation dropped."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    """Every heading anchor in `text`, with `-1`, `-2` appended to repeated headings."""
    seen: dict[str, int] = {}
    result: set[str] = set()
    for line in lines_outside_fences(text):
        match = _HEADING.match(line)
        if match is None:
            continue
        base = slug(match.group(1))
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


def _target_problem(source: Path, relative_file: str, target: str) -> str | None:
    path_part, _, anchor = target.partition("#")
    destination = source if path_part == "" else (source.parent / path_part)
    if not destination.exists():
        return f"{relative_file}: {target} does not exist"
    if anchor and destination.suffix == ".md" and anchor not in anchors(destination.read_text()):
        return f"{relative_file}: {target} — no such anchor"
    return None


def link_problems(repo: Path, relative_file: str) -> list[str]:
    """One message per relative link in `repo / relative_file` whose file or anchor is missing."""
    source = repo / relative_file
    text = source.read_text()
    targets = [*_MD_LINK.findall(text), *_HTML_REF.findall(text)]
    checked = (
        _target_problem(source, relative_file, target)
        for target in targets
        if not _ABSOLUTE_URL.match(target)
    )
    return [problem for problem in checked if problem is not None]
