from unittest.mock import patch

import build_blocklist
import pytest


def test_confirm_write_yes_returns_true():
    with patch("builtins.input", return_value="y"):
        assert build_blocklist._confirm_write(["recruiter"]) is True


def test_confirm_write_sim_returns_true():
    with patch("builtins.input", return_value="sim"):
        assert build_blocklist._confirm_write(["recruiter"]) is True


def test_confirm_write_empty_input_defaults_to_false():
    """S-10: silence is never consent — the default is 'no'."""
    with patch("builtins.input", return_value=""):
        assert build_blocklist._confirm_write(["recruiter"]) is False


def test_confirm_write_no_returns_false():
    with patch("builtins.input", return_value="n"):
        assert build_blocklist._confirm_write(["recruiter"]) is False


async def test_run_skips_write_without_confirmation(tmp_path, monkeypatch):
    """assume_yes=False and the user declines -> blocklist_learned.yaml is never written."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    async def fake_propose(company, titles, threshold, caller, model, profile):
        return [{"pattern": "recruiter", "examples": ["Recruiter"], "safe": True, "reasoning": "x"}]

    with (
        patch.object(build_blocklist, "_fetch_low_scorers", return_value={"Acme": ["Recruiter"]}),
        patch.object(build_blocklist, "_propose_for_company", new=fake_propose),
        patch.object(
            build_blocklist, "make_caller", return_value=lambda *_arguments, **_keywords: None
        ),
        patch("builtins.input", return_value="n"),
    ):
        await build_blocklist._run(3.0, None, False, "model", {}, {}, assume_yes=False)

    assert not (tmp_path / "blocklist_learned.yaml").exists()


async def test_run_writes_with_yes_flag_and_never_prompts(tmp_path, monkeypatch):
    """assume_yes=True writes without EVER calling input() (non-interactive use)."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    async def fake_propose(company, titles, threshold, caller, model, profile):
        return [{"pattern": "recruiter", "examples": ["Recruiter"], "safe": True, "reasoning": "x"}]

    with (
        patch.object(build_blocklist, "_fetch_low_scorers", return_value={"Acme": ["Recruiter"]}),
        patch.object(build_blocklist, "_propose_for_company", new=fake_propose),
        patch.object(
            build_blocklist, "make_caller", return_value=lambda *_arguments, **_keywords: None
        ),
        patch("builtins.input", side_effect=AssertionError("must not prompt with --yes")),
    ):
        await build_blocklist._run(3.0, None, False, "model", {}, {}, assume_yes=True)

    assert (tmp_path / "blocklist_learned.yaml").exists()


async def test_run_dry_run_never_prompts_either(tmp_path, monkeypatch):
    """--dry-run never writes or prompts, regardless of assume_yes."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    async def fake_propose(company, titles, threshold, caller, model, profile):
        return [{"pattern": "recruiter", "examples": ["Recruiter"], "safe": True, "reasoning": "x"}]

    with (
        patch.object(build_blocklist, "_fetch_low_scorers", return_value={"Acme": ["Recruiter"]}),
        patch.object(build_blocklist, "_propose_for_company", new=fake_propose),
        patch.object(
            build_blocklist, "make_caller", return_value=lambda *_arguments, **_keywords: None
        ),
        patch("builtins.input", side_effect=AssertionError("must not prompt on --dry-run")),
    ):
        await build_blocklist._run(3.0, None, True, "model", {}, {}, assume_yes=False)

    assert not (tmp_path / "blocklist_learned.yaml").exists()


def test_load_learned_without_a_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    assert build_blocklist._load_learned() == []


@pytest.mark.parametrize("content", ["", "other_key: [x]\n"])
def test_load_learned_tolerates_an_empty_file_and_a_missing_key(tmp_path, monkeypatch, content):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "blocklist_learned.yaml").write_text(content)

    assert build_blocklist._load_learned() == []


def test_save_learned_merges_without_duplicates_keeping_the_order(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "blocklist_learned.yaml").write_text("title_blocklist:\n- b\n- a\n")

    build_blocklist._save_learned(["c", "a", "c", "d"])

    assert (tmp_path / "blocklist_learned.yaml").read_text() == (
        "title_blocklist:\n- b\n- a\n- c\n- d\n"
    )


def test_save_learned_creates_the_home_directory(tmp_path, monkeypatch):
    home = tmp_path / "missing" / "home"
    monkeypatch.setenv("MOONLIGHTER_HOME", str(home))

    build_blocklist._save_learned(["ação"])

    assert (home / "blocklist_learned.yaml").read_text(encoding="utf-8") == (
        "title_blocklist:\n- ação\n"
    )
