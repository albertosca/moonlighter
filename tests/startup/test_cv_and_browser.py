"""A missing CV or browser is a warning that names the path the application would use."""

from moonlighter.startup import validate_startup


def test_validate_startup_missing_cv_produces_warn(tmp_path):
    warnings = validate_startup(
        config={},
        profile={"skills": []},
        cv_path=str(tmp_path / "nonexistent.pdf"),
    )
    assert any(warning.level == "warn" and "cv" in warning.message.lower() for warning in warnings)


def test_validate_startup_default_cv_path_resolves_under_moonlighter_home(monkeypatch, tmp_path):
    """When cv_path is omitted, the default is <MOONLIGHTER_HOME>/cv.pdf, not a path
    relative to the installed package (which is an ephemeral cache dir under uvx).
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    warnings = validate_startup(config={}, profile={"skills": []})
    cv_warning = next(warning for warning in warnings if "cv" in warning.message.lower())
    assert str(tmp_path / "cv.pdf") in cv_warning.message


def test_validate_startup_honours_a_configured_cv_default(tmp_path):
    """A user who points cv.default somewhere else must not be told their CV is
    missing -- the composer resolves the CV through config, so the warning must too.
    """
    resume = tmp_path / "resumes" / "senior.pdf"
    resume.parent.mkdir()
    resume.touch()
    warnings = validate_startup(
        config={"cv": {"default": str(resume)}},
        profile={"skills": []},
    )
    assert not any("cv" in warning.message.lower() for warning in warnings)


def test_validate_startup_names_the_configured_cv_when_it_is_missing(tmp_path):
    """And when it really is missing, the warning names the configured path --
    not MOONLIGHTER_HOME/cv.pdf, which the applier would never have looked at.
    """
    configured = tmp_path / "resumes" / "senior.pdf"
    warnings = validate_startup(
        config={"cv": {"default": str(configured)}},
        profile={"skills": []},
    )
    cv_warning = next(warning for warning in warnings if "cv" in warning.message.lower())
    assert str(configured) in cv_warning.message


def test_validate_startup_resolves_a_relative_cv_default_from_moonlighter_home(
    monkeypatch, tmp_path
):
    """Relative cv.default resolves from MOONLIGHTER_HOME, matching resolve_cv_path."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    resume = tmp_path / "my-cv.pdf"
    resume.touch()
    warnings = validate_startup(
        config={"cv": {"default": "my-cv.pdf"}},
        profile={"skills": []},
    )
    assert not any("cv" in warning.message.lower() for warning in warnings)


def test_validate_startup_cv_present_no_cv_warning(tmp_path):
    resume = tmp_path / "cv.pdf"
    resume.touch()
    warnings = validate_startup(
        config={},
        profile={"skills": []},
        cv_path=str(resume),
    )
    assert not any("cv" in warning.message.lower() for warning in warnings)


def test_validate_startup_missing_browser_produces_warn():
    warnings = validate_startup(
        config={"browser_path": "/nonexistent/Chrome"},
        profile={"skills": []},
    )
    assert any(
        warning.level == "warn" and "browser" in warning.message.lower() for warning in warnings
    )


def test_validate_startup_legacy_brave_path_still_works(tmp_path):
    """Backwards compat: the legacy brave_path key is still recognized (via browser_executable)."""
    brave = tmp_path / "brave"
    brave.touch()
    warnings = validate_startup(
        config={"brave_path": str(brave)},
        profile={"skills": []},
    )
    assert not any("browser" in warning.message.lower() for warning in warnings)
