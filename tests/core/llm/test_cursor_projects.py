from pathlib import Path

import pytest

from moonlighter.core.llm.cursor_projects import (
    _cursor_project_slug,
    _cursor_projects_for,
    _cursor_projects_root,
    forget_cursor_call,
)

pytestmark = pytest.mark.usefixtures("_no_real_cursor_projects")


def test_cursor_project_slug_matches_the_directory_cursor_creates():
    """Dots and underscores are dashes, and a doubled dash collapses. A path
    under ~/.moonlighter misses the real directory if either rule is dropped.
    """
    assert (
        _cursor_project_slug(Path("/Users/ada/.moonlighter/cli-workdir"))
        == "Users-ada-moonlighter-cli-workdir"
    )
    assert (
        _cursor_project_slug(Path("/var/folders/x/abc_def/T/tmp.token"))
        == "var-folders-x-abc-def-T-tmp-token"
    )


def test_forget_cursor_call_removes_the_project_named_after_the_workspace(tmp_path, monkeypatch):
    r"""The jsonl stores a newline as the two characters \n, so matching the
    prompt text misses every real prompt. The trust file names the workspace,
    and that is what selects the project. A stranger project stays.
    """
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm.cursor_projects._cursor_projects_root", lambda: root)
    workdir = tmp_path / "cursor-one"
    workdir.mkdir()
    prompt = "first line\nTOKEN_ONE"
    project = root / _cursor_project_slug(workdir)
    transcripts = project / "agent-transcripts"
    transcripts.mkdir(parents=True)
    (transcripts / "a.jsonl").write_text(prompt.replace("\n", "\\n"))
    (project / ".workspace-trusted").write_text('{"workspacePath": "' + str(workdir) + '"}')
    stranger = root / "other-editor-session" / "agent-transcripts"
    stranger.mkdir(parents=True)
    (stranger / "c.jsonl").write_text("brand new but unrelated")

    forget_cursor_call(workdir)

    assert not project.exists()
    assert not workdir.exists()
    assert (stranger / "c.jsonl").read_text() == "brand new but unrelated"


def test_forget_cursor_call_finds_a_project_whose_name_is_not_the_slug(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm.cursor_projects._cursor_projects_root", lambda: root)
    workdir = tmp_path / "cursor-two"
    workdir.mkdir()
    project = root / "whatever-the-cli-picked"
    (project / "agent-transcripts").mkdir(parents=True)
    (project / "agent-transcripts" / "a.jsonl").write_text("first line\\nTOKEN_TWO")
    (project / ".workspace-trusted").write_text(str(workdir.resolve()))
    untouched = root / "no-trust-file"
    untouched.mkdir()
    decoy = root / "other-workspace"
    decoy.mkdir()
    (decoy / ".workspace-trusted").write_text("/somewhere/else")
    (root / "not-a-project").write_text("ignored")

    forget_cursor_call(workdir)

    assert not project.exists()
    assert untouched.is_dir()
    assert (decoy / ".workspace-trusted").read_text() == "/somewhere/else"
    assert not workdir.exists()


def test_forget_cursor_call_skips_an_unreadable_trust_file(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm.cursor_projects._cursor_projects_root", lambda: root)
    workdir = tmp_path / "cursor-three"
    workdir.mkdir()
    unreadable = root / "unreadable"
    unreadable.mkdir()
    (unreadable / ".workspace-trusted").write_text(str(workdir))
    readable = root / "readable"
    readable.mkdir()
    (readable / ".workspace-trusted").write_text(str(workdir))
    original = Path.read_text

    def read_text(self: Path, *positional_arguments: object, **keyword_arguments: object) -> str:
        if self.parent == unreadable:
            raise OSError("gone")
        return original(self, *positional_arguments, **keyword_arguments)

    monkeypatch.setattr(Path, "read_text", read_text)

    assert _cursor_projects_for(workdir) == [readable]


def test_forget_cursor_call_gives_up_when_listing_projects_fails(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm.cursor_projects._cursor_projects_root", lambda: root)
    workdir = tmp_path / "cursor-four"
    workdir.mkdir()

    def iterdir(self: Path):
        if self == root:
            raise OSError("denied")
        return []

    monkeypatch.setattr(Path, "iterdir", iterdir)

    assert _cursor_projects_for(workdir) == []
    forget_cursor_call(workdir)
    assert not workdir.exists()


def test_forget_cursor_call_is_a_no_op_when_nothing_is_there(tmp_path, monkeypatch):
    missing = tmp_path / "absent"
    monkeypatch.setattr(
        "moonlighter.core.llm.cursor_projects._cursor_projects_root", lambda: missing
    )
    forget_cursor_call(tmp_path / "workdir")


def test_cursor_projects_root_is_the_home_projects_dir():
    assert _cursor_projects_root() == Path.home() / ".cursor" / "projects"


def test_cursor_projects_for_lists_a_trusted_slug_project_once(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm.cursor_projects._cursor_projects_root", lambda: root)
    workdir = (tmp_path / "cursor-five").resolve()
    workdir.mkdir()
    project = root / _cursor_project_slug(workdir)
    project.mkdir()
    (project / ".workspace-trusted").write_text(str(workdir))

    assert _cursor_projects_for(workdir) == [project]


def test_cursor_projects_for_stops_at_the_slug_project_when_it_matches(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm.cursor_projects._cursor_projects_root", lambda: root)
    workdir = (tmp_path / "cursor-six").resolve()
    workdir.mkdir()
    project = root / _cursor_project_slug(workdir)
    elsewhere = root / "also-trusts-it"
    for trusting in (project, elsewhere):
        trusting.mkdir()
        (trusting / ".workspace-trusted").write_text(str(workdir))

    assert _cursor_projects_for(workdir) == [project]
