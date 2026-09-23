import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _srd():
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import stamp_revision_dates

    return stamp_revision_dates


def _git(repo: Path, *args: str, date: str | None = None) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00"
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)  # noqa: S603, S607 - literal argv, git on PATH


def _repo_with_two_pages(root: Path) -> Path:
    guide = root / "guide" / "en"
    guide.mkdir(parents=True)
    _git(root, "init", "-q")
    (guide / "old.md").write_text("# Old\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "old", date="2026-01-15")
    (guide / "new.md").write_text("# New\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "new", date="2026-03-02")
    return root


def test_page_without_frontmatter_gains_one():
    assert (
        _srd().with_revision_date("# T\n", "2026-01-15")
        == "---\nrevision_date: 2026-01-15\n---\n# T\n"
    )


def test_existing_frontmatter_gains_the_key_once():
    out = _srd().with_revision_date("---\ntitle: X\n---\n# T\n", "2026-01-15")
    assert out == "---\ntitle: X\nrevision_date: 2026-01-15\n---\n# T\n"


def test_empty_frontmatter_block():
    assert (
        _srd().with_revision_date("---\n---\n# T\n", "2026-01-15")
        == "---\nrevision_date: 2026-01-15\n---\n# T\n"
    )


def test_existing_revision_date_is_replaced():
    out = _srd().with_revision_date("---\nrevision_date: 2020-01-01\n---\n# T\n", "2026-01-15")
    assert out.count("revision_date") == 1 and "2026-01-15" in out


def test_each_page_gets_its_own_last_commit_date(tmp_path):
    repo = _repo_with_two_pages(tmp_path)
    assert _srd().stamp(repo / "guide") == 2
    assert "revision_date: 2026-01-15" in (repo / "guide/en/old.md").read_text()
    assert "revision_date: 2026-03-02" in (repo / "guide/en/new.md").read_text()


def test_shallow_clone_is_refused(tmp_path):
    repo = _repo_with_two_pages(tmp_path / "origin")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(clone)], check=True)  # noqa: S603, S607 - literal argv, git on PATH
    with pytest.raises(_srd().StampError, match="shallow"):
        _srd().stamp(clone / "guide")
    assert "revision_date" not in (clone / "guide/en/old.md").read_text()


def test_uncommitted_page_is_an_error_naming_it(tmp_path):
    repo = _repo_with_two_pages(tmp_path)
    (repo / "guide/en/draft.md").write_text("# Draft\n")
    with pytest.raises(_srd().StampError, match=r"draft\.md"):
        _srd().stamp(repo / "guide")


def test_main_reports_errors_with_exit_1(tmp_path, capsys):
    repo = _repo_with_two_pages(tmp_path)
    (repo / "guide/en/draft.md").write_text("# Draft\n")
    assert _srd().main(["x", str(repo / "guide")]) == 1
    assert "draft.md" in capsys.readouterr().err
