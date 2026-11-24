"""With llm_backend opencode, startup checks that opencode lists the configured models."""

from unittest.mock import Mock

import pytest

from moonlighter.core.config.loading import build_config
from moonlighter.startup import validate_startup

OPENCODE_CONFIG = {
    "llm_backend": "opencode",
    "llm_model": "anthropic/claude-sonnet-5-5",
    "eval_model": "anthropic/claude-haiku-5-5",
}
BOTH_MODELS = ["anthropic/claude-haiku-5-5", "anthropic/claude-sonnet-5-5", "fake/echo"]


@pytest.fixture
def listing(monkeypatch):
    monkeypatch.setattr("moonlighter.startup.opencode_executable", lambda: "/opt/bin/opencode")
    listed = Mock(return_value=BOTH_MODELS)
    monkeypatch.setattr("moonlighter.startup.list_opencode_models", listed)
    return listed


def _messages(config=OPENCODE_CONFIG):
    return validate_startup(config=build_config(config), profile={"skills": []})


def _opencode_warnings(config=OPENCODE_CONFIG):
    return [warning for warning in _messages(config) if "opencode" in warning.message]


def test_both_models_listed_is_quiet(listing):
    assert _opencode_warnings() == []
    listing.assert_called_once_with("/opt/bin/opencode")


def test_a_model_opencode_does_not_list_is_an_error(listing):
    listing.return_value = ["anthropic/claude-haiku-5-5"]
    (warning,) = _opencode_warnings()
    assert warning.level == "error"
    assert "anthropic/claude-sonnet-5-5" in warning.message
    assert "anthropic/claude-haiku-5-5" not in warning.message
    assert "opencode auth login" in warning.message
    assert "hand-declared provider" in warning.message


def test_a_listing_that_failed_is_a_warning(listing):
    listing.return_value = None
    (warning,) = _opencode_warnings()
    assert warning.level == "warn"
    assert "could not be checked" in warning.message


def test_a_missing_binary_reports_only_the_binary(listing, monkeypatch):
    monkeypatch.setattr("moonlighter.startup.opencode_executable", lambda: None)
    (warning,) = _opencode_warnings()
    assert "not found on PATH" in warning.message
    listing.assert_not_called()


def test_another_backend_never_lists(listing):
    _messages({"llm_backend": "cli"})
    listing.assert_not_called()


def test_an_unmeasured_opencode_version_is_a_warning(listing, monkeypatch):
    monkeypatch.setattr("moonlighter.startup.version_drift", lambda _: "opencode 3.0.0 differs")
    (warning,) = _opencode_warnings()
    assert warning.level == "warn"
    assert warning.message == "opencode 3.0.0 differs"


def test_another_backend_never_asks_for_the_version(listing, monkeypatch):
    drift = Mock(return_value="drift")
    monkeypatch.setattr("moonlighter.startup.version_drift", drift)
    _messages({"llm_backend": "cli"})
    drift.assert_not_called()
