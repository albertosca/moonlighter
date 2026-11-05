import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from moonlighter.discovery import cli
from moonlighter.discovery.cli import _run, parse_args
from moonlighter.discovery.results import ScanKind, ScanReport


@contextmanager
def _patched(report):
    """Patches discovery.cli's bootstrap/make_caller/scan_and_evaluate/scan_company together.

    All return `report` from whichever scan function _run calls -- only one of the two scan
    functions runs per test, patching the other one is harmless.
    """
    with (
        patch.object(cli, "bootstrap", return_value=({"score_threshold": 6.5}, {})),
        patch.object(cli, "make_caller", return_value=object()),
        patch.object(cli, "scan_and_evaluate", new=AsyncMock(return_value=report)),
        patch.object(cli, "scan_company", new=AsyncMock(return_value=report)),
    ):
        yield


def test_parse_args_defaults_and_no_eval():
    parsed_arguments = parse_args([])
    assert (
        parsed_arguments.keywords,
        parsed_arguments.phase,
        parsed_arguments.no_eval,
        parsed_arguments.company,
    ) == (
        "",
        "phase1",
        False,
        None,
    )
    assert parse_args(["--no-eval", "--phase", "all"]).no_eval is True
    assert parse_args(["--company", "greenhouse", "acme"]).company == ["greenhouse", "acme"]


def test_parse_args_rejects_a_phase_outside_the_configured_set(capsys):
    # A free-text --phase silently scans zero companies (load_company_list's
    # value.get(phase, [])) and produces the same no_new_jobs JSON as a
    # genuinely quiet day -- a cron never learns it is scanning nothing.

    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--phase", "phase9"])
    assert exit_info.value.code == 2
    # JsonArgumentParser: stdout still carries the contract's one JSON
    # document, not zero bytes, even on a bad flag.
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "usage_error"


async def test_run_evaluated_scan_exits_0_with_the_report_as_json(temporary_database):
    report = ScanReport(kind=ScanKind.EVALUATED, threshold=6.5)
    with _patched(report):
        payload, code = await _run(parse_args([]))
    assert code == 0
    assert payload["kind"] == "evaluated"
    json.dumps(payload)


async def test_run_nothing_new_exits_1(temporary_database):
    report = ScanReport(kind=ScanKind.NO_NEW_JOBS, threshold=6.5)
    with _patched(report):
        payload, code = await _run(parse_args([]))
    assert (payload["kind"], code) == ("no_new_jobs", 1)


async def test_run_unknown_source_exits_2(temporary_database):
    report = ScanReport(
        kind=ScanKind.UNKNOWN_SOURCE, threshold=6.5, error="Unknown source 'lever'."
    )
    with _patched(report):
        payload, code = await _run(parse_args(["--company", "lever", "acme"]))
    assert (payload["kind"], code) == ("unknown_source", 2)
    assert payload["error"].startswith("Unknown source")


async def test_run_no_eval_passes_no_caller_to_the_service(temporary_database):
    # The whole point of --no-eval: make_caller is never even constructed.

    report = ScanReport(kind=ScanKind.NO_NEW_JOBS, threshold=6.5)
    scan = AsyncMock(return_value=report)
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "make_caller", side_effect=AssertionError("must not be called")),
        patch.object(cli, "scan_and_evaluate", new=scan),
    ):
        await _run(parse_args(["--no-eval"]))
    assert scan.await_args.args[-1] is cli.NO_EVAL


def test_scan_keeps_its_flag_grammar_and_gains_doctor():
    assert parse_args([]).command == "run"
    assert parse_args(["--no-eval", "--phase", "all"]).command == "run"
    assert parse_args(["--company", "greenhouse", "acme"]).company == ["greenhouse", "acme"]
    assert parse_args(["doctor"]).command == "doctor"


async def test_scan_doctor_returns_the_doctor_payload(temporary_database):
    with patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)):
        payload, code = await cli._run(cli.parse_args(["doctor"]))
    assert (payload, code) == ({"kind": "doctor"}, 0)


def test_scan_help_carries_the_slice_epilog(capsys):
    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--help"])
    assert exit_info.value.code == 0
    assert "installed:" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("kind", "extra"),
    [
        (ScanKind.ALL_KNOWN, {"company": "acme", "found_but_known": 2}),
        (ScanKind.NO_OPEN_JOBS, {"company": "acme"}),
    ],
)
async def test_run_with_nothing_to_report_for_a_company_exits_1(temporary_database, kind, extra):
    with _patched(ScanReport(kind=kind, threshold=6.5, **extra)):
        payload, code = await _run(parse_args(["--company", "greenhouse", "acme"]))
    assert (payload["kind"], code) == (kind.value, 1)
