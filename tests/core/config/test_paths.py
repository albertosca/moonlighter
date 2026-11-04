from pathlib import Path

from moonlighter.core.config import browser_executable, moonlighter_home, resolve_under_home


def test_browser_executable_prefers_browser_path():
    assert browser_executable({"browser_path": "/usr/bin/chrome"}) == "/usr/bin/chrome"


def test_browser_executable_falls_back_to_legacy_brave_path():
    assert (
        browser_executable({"browser_path": "", "brave_path": "/legacy/brave"}) == "/legacy/brave"
    )
    assert browser_executable({"brave_path": "/legacy/brave"}) == "/legacy/brave"
    assert browser_executable({}) == ""


def test_moonlighter_home_default(monkeypatch):
    monkeypatch.delenv("MOONLIGHTER_HOME", raising=False)
    home = moonlighter_home()
    assert home == (Path.home() / ".moonlighter")


def test_moonlighter_home_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert moonlighter_home() == tmp_path


def test_resolve_under_home_joins_a_relative_path_onto_moonlighter_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert resolve_under_home("gmail-client.json") == tmp_path / "gmail-client.json"


def test_resolve_under_home_leaves_an_absolute_path_untouched(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "not-this-one"))
    absolute = tmp_path / "elsewhere" / "creds.json"
    assert resolve_under_home(str(absolute)) == absolute


def test_resolve_under_home_expands_a_tilde_path_without_touching_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "not-this-one"))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert resolve_under_home("~/creds.json") == tmp_path / "creds.json"
