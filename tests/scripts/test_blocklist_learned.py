from unittest.mock import patch

import pytest

import blocklist_learned


def test_confirm_write_yes_returns_true():
    with patch("builtins.input", return_value="y"):
        assert blocklist_learned.confirm_write(["recruiter"]) is True


def test_confirm_write_sim_returns_true():
    with patch("builtins.input", return_value="sim"):
        assert blocklist_learned.confirm_write(["recruiter"]) is True


def test_confirm_write_empty_input_defaults_to_false():
    """S-10: silence is never consent — the default is 'no'."""
    with patch("builtins.input", return_value=""):
        assert blocklist_learned.confirm_write(["recruiter"]) is False


def test_confirm_write_no_returns_false():
    with patch("builtins.input", return_value="n"):
        assert blocklist_learned.confirm_write(["recruiter"]) is False


def test_load_learned_without_a_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    assert blocklist_learned.load_learned() == []


@pytest.mark.parametrize("content", ["", "other_key: [x]\n"])
def test_load_learned_tolerates_an_empty_file_and_a_missing_key(tmp_path, monkeypatch, content):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "blocklist_learned.yaml").write_text(content)

    assert blocklist_learned.load_learned() == []


def test_save_learned_merges_without_duplicates_keeping_the_order(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "blocklist_learned.yaml").write_text("title_blocklist:\n- b\n- a\n")

    blocklist_learned.save_learned(["c", "a", "c", "d"])

    assert (tmp_path / "blocklist_learned.yaml").read_text() == (
        "title_blocklist:\n- b\n- a\n- c\n- d\n"
    )


def test_save_learned_creates_the_home_directory(tmp_path, monkeypatch):
    home = tmp_path / "missing" / "home"
    monkeypatch.setenv("MOONLIGHTER_HOME", str(home))

    blocklist_learned.save_learned(["ação"])

    assert (home / "blocklist_learned.yaml").read_text(encoding="utf-8") == (
        "title_blocklist:\n- ação\n"
    )
