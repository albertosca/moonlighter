"""The doctor subcommand: offline by default, link report under --online, load failures reported."""

from unittest.mock import AsyncMock, patch

import pytest
import yaml
from moonlighter.application import cli
from moonlighter.application.commands import doctor as doctor_command
from moonlighter.core.config.errors import ConfigError


async def test_apply_doctor_returns_the_doctor_payload(temporary_database):
    with patch.object(doctor_command, "doctor_payload", return_value=({"kind": "doctor"}, 0)):
        payload, code = await cli._run(cli.parse_args(["doctor"]))
    assert (payload, code) == ({"kind": "doctor"}, 0)


async def test_apply_doctor_stays_offline_without_the_flag(temporary_database):
    report = AsyncMock()
    with (
        patch.object(doctor_command, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(doctor_command, "link_report", report),
    ):
        payload, _ = await cli._run(cli.parse_args(["doctor"]))
    report.assert_not_awaited()
    assert "links" not in payload


async def test_apply_doctor_online_reports_the_cv_links_and_fails_on_a_broken_one(
    temporary_database,
):
    links = [
        {"url": "https://github.com/albertosca", "status": 200, "ok": True, "note": None},
        {"url": "https://github.com/albertoalbuquerque", "status": 404, "ok": False, "note": None},
    ]
    with (
        patch.object(doctor_command, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(doctor_command, "link_report", AsyncMock(return_value=links)),
    ):
        payload, code = await cli._run(cli.parse_args(["doctor", "--online"]))
    assert payload["links"] == links
    assert code == 1


async def test_apply_doctor_online_keeps_exit_0_when_links_are_fine_or_unverified(
    temporary_database,
):
    links = [{"url": "https://www.linkedin.com/in/x", "status": 999, "ok": None, "note": "n"}]
    with (
        patch.object(doctor_command, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(doctor_command, "link_report", AsyncMock(return_value=links)),
    ):
        _, code = await cli._run(cli.parse_args(["doctor", "--online"]))
    assert code == 0


async def test_apply_doctor_online_reports_a_broken_config_instead_of_crashing(
    temporary_database,
):
    """--online exists to diagnose; a config that does not load must come back in
    the payload the way plain doctor reports it, not as a crash (exit 3)."""
    report = AsyncMock()
    with (
        patch.object(doctor_command, "doctor_payload", return_value=({"kind": "doctor"}, 1)),
        patch.object(doctor_command, "load_config", side_effect=yaml.YAMLError("bad yaml")),
        patch.object(doctor_command, "link_report", report),
    ):
        payload, code = await cli._run(cli.parse_args(["doctor", "--online"]))
    report.assert_not_awaited()
    assert payload["links"] is None
    assert "bad yaml" in payload["links_error"]
    assert code == 1


async def test_apply_doctor_online_says_when_there_was_nothing_to_check(temporary_database):
    """An empty list read the same as "every link works" (2026-09-29 review)."""
    with (
        patch.object(doctor_command, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(doctor_command, "link_report", AsyncMock(return_value=[])),
    ):
        payload, code = await cli._run(cli.parse_args(["doctor", "--online"]))
    assert payload["links"] == []
    assert "no CV template" in payload["links_note"]
    assert code == 0


@pytest.mark.parametrize(
    "failure", [ConfigError("bad config"), OSError("bad disk"), yaml.YAMLError("bad yaml")]
)
async def test_apply_doctor_online_reports_every_load_failure_with_the_same_prefix(
    temporary_database, failure
):
    with (
        patch.object(doctor_command, "doctor_payload", return_value=({"kind": "doctor"}, 1)),
        patch.object(doctor_command, "load_config", side_effect=failure),
    ):
        payload, code = await cli._run(cli.parse_args(["doctor", "--online"]))
    assert payload["links"] is None
    assert payload["links_error"] == f"config does not load: {failure}"
    assert "links_note" not in payload
    assert code == 1


async def test_apply_doctor_online_nothing_to_check_note_is_this_exact_sentence(
    temporary_database,
):
    with (
        patch.object(doctor_command, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(doctor_command, "link_report", AsyncMock(return_value=[])),
    ):
        payload, _ = await cli._run(cli.parse_args(["doctor", "--online"]))
    assert payload["links_note"] == (
        "no CV template with header links found in cv.template_dir; nothing checked"
    )
