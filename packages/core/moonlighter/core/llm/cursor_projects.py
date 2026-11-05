"""Cursor's project bookkeeping: find the project directory a call created, and remove it."""

import re
from pathlib import Path

from moonlighter.core.llm.isolation import remove_quietly


def _cursor_projects_root() -> Path:
    return Path.home() / ".cursor" / "projects"


def _cursor_project_slug(path: Path) -> str:
    """Directory name Cursor gives a workspace.

    The absolute path, no leading slash. `/`, `.` and `_` each become a dash,
    and a run of dashes collapses to one: `~/.moonlighter` would otherwise stay
    a dotted name the CLI does not create. Checked against project directories
    the CLI wrote on macOS. A name that still does not match is found by
    `.workspace-trusted`.
    """
    slug = str(path).lstrip("/").replace("/", "-").replace(".", "-").replace("_", "-")
    return re.sub(r"-{2,}", "-", slug)


def _trust_names(project: Path, marks: set[str]) -> bool:
    """True when this project's `.workspace-trusted` quotes the workdir."""
    trusted = project / ".workspace-trusted"
    try:
        if not trusted.is_file():
            return False
        text = trusted.read_text(errors="replace")
    except OSError:
        return False
    return any(mark in text for mark in marks)


def _candidate_projects(root: Path, workdir: Path, marks: set[str]) -> list[Path]:
    """The projects named after the workdir when one of them is trusted, else every project.

    A listing that fails yields no candidates: cleanup gives up rather than raise.
    """
    named = [root / _cursor_project_slug(path) for path in (workdir, workdir.resolve())]
    if any(_trust_names(path, marks) for path in named):
        return named
    try:
        return [path for path in root.iterdir() if path.is_dir()]
    except OSError:
        return []


def _cursor_projects_for(workdir: Path) -> list[Path]:
    """Project dirs this call created.

    The usual name is the workspace path with slashes turned into dashes, and
    `.workspace-trusted` quotes that path. A miss on the computed name reads
    that one file in each project, not every transcript under the tree.
    """
    root = _cursor_projects_root()
    if not root.is_dir():
        return []
    marks = {str(workdir), str(workdir.resolve())}
    found: list[Path] = []
    for project in _candidate_projects(root, workdir, marks):
        if project not in found and _trust_names(project, marks):
            found.append(project)
    return found


def forget_cursor_call(workdir: Path) -> None:
    """Remove this call's Cursor project directory and its private workdir."""
    for project in _cursor_projects_for(workdir):
        remove_quietly(project)
    remove_quietly(workdir)
