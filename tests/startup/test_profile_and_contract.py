"""An empty profile, an unknown location precedence, and the all-clear and return-type contracts."""

import pytest
from moonlighter.startup import StartupWarning, validate_startup


def test_validate_startup_empty_profile_produces_warn():
    warnings = validate_startup(config={}, profile={})
    assert any(
        warning.level == "warn" and "profile" in warning.message.lower() for warning in warnings
    )


def test_validate_startup_non_empty_profile_no_profile_warning():
    warnings = validate_startup(config={}, profile={"skills": [{"name": "Python"}]})
    assert not any("profile" in warning.message.lower() for warning in warnings)


@pytest.mark.parametrize("value", ["Generic", "specfic", "global"])
def test_an_unknown_location_precedence_warns_and_names_the_valid_values(value):
    """A typo silently meant "specific" (2026-09-29 review): say so at startup."""
    profile = {"criteria": {"location_precedence": value}}
    warnings = validate_startup(config={}, profile=profile)
    messages = [warning.message for warning in warnings if "location_precedence" in warning.message]
    assert len(messages) == 1
    assert value in messages[0]
    assert "specific" in messages[0]
    assert "generic" in messages[0]


@pytest.mark.parametrize(
    "profile", [{"criteria": {"location_precedence": "generic"}}, {"criteria": {}}, {"skills": []}]
)
def test_a_valid_or_absent_location_precedence_is_quiet(profile):
    warnings = validate_startup(config={}, profile=profile)
    assert not any("location_precedence" in warning.message for warning in warnings)


def test_validate_startup_all_ok_returns_no_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    browser = tmp_path / "chrome"
    browser.touch()
    resume = tmp_path / "cv.pdf"
    resume.touch()
    warnings = validate_startup(
        config={"browser_path": str(browser)},
        profile={"skills": [{"name": "Python"}]},
        cv_path=str(resume),
    )
    assert not any(warning.level == "error" for warning in warnings)


def test_validate_startup_returns_list_of_startup_warnings():
    result = validate_startup(config={}, profile={})
    assert isinstance(result, list)
    assert all(isinstance(warning, StartupWarning) for warning in result)
