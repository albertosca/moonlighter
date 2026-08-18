import pytest
import yaml
from moonlighter.core.config import ConfigError, load_config
from moonlighter.init import _ask, detect_browser, run_init


def test_detect_browser_returns_first_existing(monkeypatch, tmp_path):
    present = tmp_path / "Brave Browser"
    present.write_text("")
    monkeypatch.setattr(
        "moonlighter.init._BROWSER_CANDIDATES",
        ("/nonexistent/Chrome", str(present)),
    )
    assert detect_browser() == str(present)


def test_detect_browser_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(
        "moonlighter.init._BROWSER_CANDIDATES", ("/nonexistent/a", "/nonexistent/b")
    )
    assert detect_browser() is None


def test_run_init_writes_config(tmp_path):
    path = run_init(
        tmp_path,
        {
            "browser_path": "/usr/bin/chromium",
            "citizenship_country": "Brazil",
            "llm_backend": "cli",
        },
    )
    assert path == tmp_path / "config.yaml"
    written = yaml.safe_load(path.read_text())
    assert written["browser_path"] == "/usr/bin/chromium"
    assert written["work_authorization"]["citizenship_country"] == "Brazil"
    assert written["llm_backend"] == "cli"


def test_run_init_creates_home_when_missing(tmp_path):
    home = tmp_path / "nested" / "home"
    run_init(home, {"browser_path": "", "citizenship_country": "", "llm_backend": "cli"})
    assert home.is_dir()


def test_run_init_refuses_to_overwrite(tmp_path):
    (tmp_path / "config.yaml").write_text("score_threshold: 9.0\n")
    with pytest.raises(FileExistsError):
        run_init(tmp_path, {"browser_path": "", "citizenship_country": "", "llm_backend": "cli"})
    assert "9.0" in (tmp_path / "config.yaml").read_text()


def test_ask_returns_typed_answer(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "  typed  ")
    assert _ask("Question", "fallback") == "typed"


def test_ask_falls_back_to_default_when_blank(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "   ")
    assert _ask("Question", "fallback") == "fallback"


def test_run_init_rejects_an_invalid_llm_backend(tmp_path):
    """The wizard must not write a config that the next boot refuses to load --
    the user would be told to fix a file they were just walked through."""
    with pytest.raises(ConfigError, match="cli, api"):
        run_init(
            tmp_path,
            {"browser_path": "/x", "citizenship_country": "Brazil", "llm_backend": "CLI"},
        )
    assert not (tmp_path / "config.yaml").exists()


def test_run_init_writes_a_config_that_loads_back(tmp_path, monkeypatch):
    """End to end: whatever the wizard writes must survive load_config's strict,
    closed-schema validation."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    browser = tmp_path / "chrome"
    browser.touch()
    path = run_init(
        tmp_path,
        {
            "browser_path": str(browser),
            "citizenship_country": "Brazil",
            "llm_backend": "cli",
        },
    )
    assert load_config(path)["llm_backend"] == "cli"
