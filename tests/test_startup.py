from moonlighter.startup import StartupWarning, validate_startup

# ── profile ───────────────────────────────────────────────────────────────────


def test_validate_startup_empty_profile_produces_warn():
    warnings = validate_startup(config={}, profile={})
    assert any(w.level == "warn" and "profile" in w.message.lower() for w in warnings)


def test_validate_startup_non_empty_profile_no_profile_warning():
    warnings = validate_startup(config={}, profile={"skills": [{"name": "Python"}]})
    assert not any("profile" in w.message.lower() for w in warnings)


# ── ANTHROPIC_API_KEY ─────────────────────────────────────────────────────────


def test_validate_startup_missing_api_key_produces_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    warnings = validate_startup(config={}, profile={"skills": []})
    assert any(w.level == "error" and "ANTHROPIC_API_KEY" in w.message for w in warnings)


def test_validate_startup_api_key_present_no_api_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    warnings = validate_startup(config={}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in w.message for w in warnings)


def test_validate_startup_cli_backend_skips_api_key_error(monkeypatch):
    """BUG-05: with llm_backend='cli' no API key is used, so its absence
    must not raise an error."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    warnings = validate_startup(config={"llm_backend": "cli"}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in w.message for w in warnings)


# ── cv.pdf ────────────────────────────────────────────────────────────────────


def test_validate_startup_missing_cv_produces_warn(tmp_path):
    warnings = validate_startup(
        config={},
        profile={"skills": []},
        cv_path=str(tmp_path / "nonexistent.pdf"),
    )
    assert any(w.level == "warn" and "cv" in w.message.lower() for w in warnings)


def test_validate_startup_default_cv_path_resolves_under_moonlighter_home(monkeypatch, tmp_path):
    """When cv_path is omitted, the default is <MOONLIGHTER_HOME>/cv.pdf, not a path
    relative to the installed package (which is an ephemeral cache dir under uvx)."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    warnings = validate_startup(config={}, profile={"skills": []})
    cv_warning = next(w for w in warnings if "cv" in w.message.lower())
    assert str(tmp_path / "cv.pdf") in cv_warning.message


def test_validate_startup_honours_a_configured_cv_default(tmp_path):
    """A user who points cv.default somewhere else must not be told their CV is
    missing -- confirm_apply resolves through config, so the warning must too."""
    cv = tmp_path / "resumes" / "senior.pdf"
    cv.parent.mkdir()
    cv.touch()
    warnings = validate_startup(
        config={"cv": {"default": str(cv)}},
        profile={"skills": []},
    )
    assert not any("cv" in w.message.lower() for w in warnings)


def test_validate_startup_names_the_configured_cv_when_it_is_missing(tmp_path):
    """And when it really is missing, the warning names the configured path --
    not MOONLIGHTER_HOME/cv.pdf, which the applier would never have looked at."""
    configured = tmp_path / "resumes" / "senior.pdf"
    warnings = validate_startup(
        config={"cv": {"default": str(configured)}},
        profile={"skills": []},
    )
    cv_warning = next(w for w in warnings if "cv" in w.message.lower())
    assert str(configured) in cv_warning.message


def test_validate_startup_resolves_a_relative_cv_default_from_moonlighter_home(
    monkeypatch, tmp_path
):
    """Relative cv.default resolves from MOONLIGHTER_HOME, matching resolve_cv_path."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    cv = tmp_path / "my-cv.pdf"
    cv.touch()
    warnings = validate_startup(
        config={"cv": {"default": "my-cv.pdf"}},
        profile={"skills": []},
    )
    assert not any("cv" in w.message.lower() for w in warnings)


def test_validate_startup_cv_present_no_cv_warning(tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.touch()
    warnings = validate_startup(
        config={},
        profile={"skills": []},
        cv_path=str(cv),
    )
    assert not any("cv" in w.message.lower() for w in warnings)


# ── browser path ──────────────────────────────────────────────────────────────


def test_validate_startup_missing_browser_produces_warn():
    warnings = validate_startup(
        config={"browser_path": "/nonexistent/Chrome"},
        profile={"skills": []},
    )
    assert any(w.level == "warn" and "browser" in w.message.lower() for w in warnings)


def test_validate_startup_legacy_brave_path_still_works(tmp_path):
    """Backwards compat: the legacy brave_path key is still recognized (via browser_executable)."""
    brave = tmp_path / "brave"
    brave.touch()
    warnings = validate_startup(
        config={"brave_path": str(brave)},
        profile={"skills": []},
    )
    assert not any("browser" in w.message.lower() for w in warnings)


# ── all clear ─────────────────────────────────────────────────────────────────


def test_validate_startup_all_ok_returns_no_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    browser = tmp_path / "chrome"
    browser.touch()
    cv = tmp_path / "cv.pdf"
    cv.touch()
    warnings = validate_startup(
        config={"browser_path": str(browser)},
        profile={"skills": [{"name": "Python"}]},
        cv_path=str(cv),
    )
    assert not any(w.level == "error" for w in warnings)


# ── return type ───────────────────────────────────────────────────────────────


def test_validate_startup_returns_list_of_startup_warnings():
    result = validate_startup(config={}, profile={})
    assert isinstance(result, list)
    assert all(isinstance(w, StartupWarning) for w in result)
