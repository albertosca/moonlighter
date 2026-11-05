import os
import subprocess
from pathlib import Path

import pytest
import stamp_revision_dates


def _git(repo: Path, *arguments: str, date: str | None = None) -> None:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    if date:
        environment["GIT_AUTHOR_DATE"] = environment["GIT_COMMITTER_DATE"] = f"{date}T12:00:00"
    subprocess.run(  # noqa: S603 - literal argv
        ["git", "-C", str(repo), *arguments],  # noqa: S607 - git on PATH
        check=True,
        capture_output=True,
        env=environment,
    )


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
        stamp_revision_dates.with_revision_date("# T\n", "2026-01-15")
        == "---\nrevision_date: 2026-01-15\n---\n# T\n"
    )


def test_existing_frontmatter_gains_the_key_once():
    out = stamp_revision_dates.with_revision_date("---\ntitle: X\n---\n# T\n", "2026-01-15")
    assert out == "---\ntitle: X\nrevision_date: 2026-01-15\n---\n# T\n"


def test_empty_frontmatter_block():
    assert (
        stamp_revision_dates.with_revision_date("---\n---\n# T\n", "2026-01-15")
        == "---\nrevision_date: 2026-01-15\n---\n# T\n"
    )


def test_existing_revision_date_is_replaced():
    out = stamp_revision_dates.with_revision_date(
        "---\nrevision_date: 2020-01-01\n---\n# T\n", "2026-01-15"
    )
    assert out.count("revision_date") == 1
    assert "2026-01-15" in out


def test_each_page_gets_its_own_last_commit_date(tmp_path):
    repo = _repo_with_two_pages(tmp_path)
    assert stamp_revision_dates.stamp(repo / "guide") == 2
    assert "revision_date: 2026-01-15" in (repo / "guide/en/old.md").read_text()
    assert "revision_date: 2026-03-02" in (repo / "guide/en/new.md").read_text()


def test_shallow_clone_is_refused(tmp_path):
    repo = _repo_with_two_pages(tmp_path / "origin")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(clone)], check=True)  # noqa: S603, S607 - literal argv, git on PATH
    with pytest.raises(stamp_revision_dates.StampError, match="shallow"):
        stamp_revision_dates.stamp(clone / "guide")
    assert "revision_date" not in (clone / "guide/en/old.md").read_text()


def test_uncommitted_page_is_an_error_naming_it(tmp_path):
    repo = _repo_with_two_pages(tmp_path)
    (repo / "guide/en/draft.md").write_text("# Draft\n")
    with pytest.raises(stamp_revision_dates.StampError, match=r"draft\.md"):
        stamp_revision_dates.stamp(repo / "guide")


def test_main_reports_errors_with_exit_1(tmp_path, capsys):
    repo = _repo_with_two_pages(tmp_path)
    (repo / "guide/en/draft.md").write_text("# Draft\n")
    assert stamp_revision_dates.main(["x", str(repo / "guide")]) == 1
    assert "draft.md" in capsys.readouterr().err


def test_main_prints_the_page_count_and_returns_zero(tmp_path, capsys):
    repo = _repo_with_two_pages(tmp_path)

    assert stamp_revision_dates.main(["x", str(repo / "guide")]) == 0

    captured = capsys.readouterr()
    assert captured.out == "Stamped 2 pages.\n"
    assert captured.err == ""


def test_main_names_the_uncommitted_page_in_its_exact_error_line(tmp_path, capsys):
    repo = _repo_with_two_pages(tmp_path)
    draft = repo / "guide/en/draft.md"
    draft.write_text("# Draft\n")

    assert stamp_revision_dates.main(["x", str(repo / "guide")]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"stamp_revision_dates: {draft.resolve()} has no commit — commit it before building the site\n"
    )


def test_one_uncommitted_page_leaves_every_other_page_unstamped(tmp_path):
    repo = _repo_with_two_pages(tmp_path)
    (repo / "guide/en/zz-draft.md").write_text("# Draft\n")  # sorts after both committed pages

    with pytest.raises(stamp_revision_dates.StampError):
        stamp_revision_dates.stamp(repo / "guide")

    assert (repo / "guide/en/old.md").read_text() == "# Old\n"
    assert (repo / "guide/en/new.md").read_text() == "# New\n"


def test_a_shallow_clone_error_line_names_the_fix(tmp_path, capsys):
    repo = _repo_with_two_pages(tmp_path / "origin")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(clone)], check=True)  # noqa: S603, S607 - literal argv, git on PATH

    assert stamp_revision_dates.main(["x", str(clone / "guide")]) == 1

    assert capsys.readouterr().err == (
        "stamp_revision_dates: shallow clone — every page would get the newest commit's date; "
        "check out with fetch-depth: 0\n"
    )


def test_an_empty_guide_directory_stamps_zero_pages(tmp_path, capsys):
    repo = _repo_with_two_pages(tmp_path)
    (repo / "empty").mkdir()

    assert stamp_revision_dates.main(["x", str(repo / "empty")]) == 0

    assert capsys.readouterr().out == "Stamped 0 pages.\n"
