"""doctor_payload reports where the state lives, whether it loads, and what each missing slice adds."""

import json
import os
from unittest.mock import patch

import pytest
from moonlighter.core.doctor import doctor_payload


def test_doctor_payload_reports_paths_slices_and_a_valid_config(monkeypatch, tmp_path):
    # No temporary_database here: doctor_payload() only checks db path existence, never
    # opens the DB, and temporary_database's MOONLIGHTER_DB_PATH override would shadow the
    # MOONLIGHTER_HOME set below, breaking the "path ends in moonlighter.db"
    # assertion.
    (tmp_path / "config.yaml").write_text("score_threshold: 7.0\n")
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    payload, code = doctor_payload()
    json.dumps(payload)
    assert code == 0
    assert payload["kind"] == "doctor"
    assert payload["home"] == str(tmp_path)
    assert payload["config"] == {
        "path": str(tmp_path / "config.yaml"),
        "exists": True,
        "valid": True,
        "error": None,
    }
    assert payload["profile"]["path"] == str(tmp_path / "profile.yaml")
    assert payload["profile"]["exists"] is False
    assert payload["db"]["path"].endswith("moonlighter.db")
    assert set(payload["slices"]) == {"scan", "apply", "email", "full"}
    assert payload["commands"] == sorted(payload["commands"])
    assert {capability["name"] for capability in payload["capabilities"]["live"]} >= {"discovery"}


def test_doctor_payload_reports_an_invalid_config_and_exits_1(
    temporary_database, monkeypatch, tmp_path
):
    (tmp_path / "config.yaml").write_text("nope: 1\n")
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    payload, code = doctor_payload()
    assert code == 1
    assert payload["config"]["valid"] is False
    assert "unknown config key 'nope'" in payload["config"]["error"]


def test_doctor_payload_reports_a_missing_config_and_exits_1(
    temporary_database, monkeypatch, tmp_path
):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    payload, code = doctor_payload()
    assert (payload["config"]["exists"], code) == (False, 1)


def test_doctor_payload_live_and_missing_capabilities_share_the_same_keys(
    temporary_database, monkeypatch, tmp_path
):
    # One payload, two object shapes was the bug: live[] carried name/commands
    # /summary, missing[] carried name/needs/summary. A consumer keying off
    # either list the same way would KeyError on the other. Both now carry
    # name, needs (sorted), commands (list), summary -- and missing[] alone
    # also carries needs_install, the subset of needs not yet installed.
    (tmp_path / "config.yaml").write_text("score_threshold: 7.0\n")
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    with patch(
        "moonlighter.core.doctor.installed_slices",
        return_value={"scan": True, "apply": False, "email": False, "full": False},
    ):
        payload, _code = doctor_payload()

    live_by_name = {
        capability["name"]: capability for capability in payload["capabilities"]["live"]
    }
    missing_by_name = {
        capability["name"]: capability for capability in payload["capabilities"]["missing"]
    }

    assert live_by_name["discovery"] == {
        "name": "discovery",
        "needs": ["scan"],
        "commands": ["moonlighter-scan"],
        "summary": "scan company boards and portals, score postings, archive closed ones",
    }
    assert missing_by_name["sheets"] == {
        "name": "sheets",
        "needs": ["apply"],
        "commands": ["moonlighter-apply prepare"],
        "summary": "compose a paste-ready application sheet, from a job id or straight from a URL",
        "needs_install": ["apply"],
    }
    # scan-to-sheet needs {scan, apply}; scan is already installed, so only
    # apply is what still needs installing.
    assert missing_by_name["scan-to-sheet"]["needs"] == ["apply", "scan"]
    assert missing_by_name["scan-to-sheet"]["needs_install"] == ["apply"]


def test_doctor_payload_keeps_the_key_order_of_every_json_object(
    temporary_database, monkeypatch, tmp_path
):
    # Dict equality ignores key order; the JSON document a script reads does
    # not. This pins the order of every object doctor emits.
    (tmp_path / "config.yaml").write_text("score_threshold: 7.0\n")
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    with patch(
        "moonlighter.core.doctor.installed_slices",
        return_value={"scan": True, "apply": False, "email": False, "full": False},
    ):
        payload, _code = doctor_payload()

    assert list(payload) == [
        "kind",
        "home",
        "config",
        "profile",
        "db",
        "slices",
        "commands",
        "capabilities",
    ]
    assert list(payload["config"]) == ["path", "exists", "valid", "error"]
    assert list(payload["profile"]) == ["path", "exists"]
    assert list(payload["db"]) == ["path", "exists"]
    assert list(payload["capabilities"]) == ["live", "missing"]
    assert [list(capability) for capability in payload["capabilities"]["live"]] == [
        ["name", "needs", "commands", "summary"],
    ]
    assert [list(capability) for capability in payload["capabilities"]["missing"]] == [
        ["name", "needs", "commands", "summary", "needs_install"],
        ["name", "needs", "commands", "summary", "needs_install"],
        ["name", "needs", "commands", "summary", "needs_install"],
        ["name", "needs", "commands", "summary", "needs_install"],
        ["name", "needs", "commands", "summary", "needs_install"],
    ]


def test_doctor_payload_lists_every_slice_a_missing_capability_still_needs_sorted(
    temporary_database, monkeypatch, tmp_path
):
    # missing[] keeps the CAPABILITIES order, and needs_install is sorted:
    # alias-round-trip needs two slices, and both are absent here.
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    with patch(
        "moonlighter.core.doctor.installed_slices",
        return_value={"scan": True, "apply": False, "email": False, "full": False},
    ):
        payload, _code = doctor_payload()

    assert [
        (capability["name"], capability["needs_install"])
        for capability in payload["capabilities"]["missing"]
    ] == [
        ("sheets", ["apply"]),
        ("tracking", ["email"]),
        ("scan-to-sheet", ["apply"]),
        ("alias-round-trip", ["apply", "email"]),
        ("mcp-server", ["full"]),
    ]


def test_doctor_payload_reports_a_malformed_yaml_config_instead_of_crashing(
    temporary_database, monkeypatch, tmp_path
):
    # load_config() reaches yaml.safe_load() before validate_config() ever
    # runs -- a syntax error there is a yaml.YAMLError, not a ConfigError, and
    # doctor_payload() must still report it as JSON instead of letting it
    # escape as a traceback (doctor's whole point is to be usable on a
    # broken install).
    (tmp_path / "config.yaml").write_text("score_threshold: [7.0\n")
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    payload, code = doctor_payload()
    assert code == 1
    assert payload["config"]["valid"] is False
    assert payload["config"]["error"] is not None
    error_lower = payload["config"]["error"].lower()
    assert "yaml" in error_lower or "pars" in error_lower or "scan" in error_lower


def test_doctor_payload_reports_an_unreadable_config_instead_of_crashing(
    temporary_database, monkeypatch, tmp_path
):
    # A chmod-000 config.yaml makes read_text() raise PermissionError, which
    # is neither a ConfigError nor a yaml.YAMLError -- doctor_payload() must
    # catch it too.
    config_path = tmp_path / "config.yaml"
    config_path.write_text("score_threshold: 7.0\n")
    config_path.chmod(0o000)
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    try:
        if os.access(config_path, os.R_OK):
            pytest.skip("running as a user that can read a chmod-000 file (e.g. root)")
        payload, code = doctor_payload()
        assert code == 1
        assert payload["config"]["valid"] is False
        assert "permission" in payload["config"]["error"].lower()
    finally:
        config_path.chmod(0o644)
