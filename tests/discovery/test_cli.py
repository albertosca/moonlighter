import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from moonlighter.discovery.results import ScanKind, ScanReport


@contextmanager
def _patched(report):
    """Patches discovery.cli's bootstrap/make_caller/scan_and_evaluate/scan_company
    together, all returning `report` from whichever scan function _run calls --
    only one of the two scan functions runs per test, patching the other one is
    harmless."""
    from moonlighter.discovery import cli

    with (
        patch.object(cli, "bootstrap", return_value=({"score_threshold": 6.5}, {})),
        patch.object(cli, "make_caller", return_value=object()),
        patch.object(cli, "scan_and_evaluate", new=AsyncMock(return_value=report)),
        patch.object(cli, "scan_company", new=AsyncMock(return_value=report)),
    ):
        yield


def test_parse_args_defaults_and_no_eval():
    from moonlighter.discovery.cli import parse_args

    args = parse_args([])
    assert (args.keywords, args.phase, args.no_eval, args.company) == ("", "phase1", False, None)
    assert parse_args(["--no-eval", "--phase", "all"]).no_eval is True
    assert parse_args(["--company", "greenhouse", "acme"]).company == ["greenhouse", "acme"]


async def test_run_evaluated_scan_exits_0_with_the_report_as_json(tmp_db):
    from moonlighter.discovery.cli import _run, parse_args

    report = ScanReport(kind=ScanKind.EVALUATED, threshold=6.5)
    with _patched(report):
        payload, code = await _run(parse_args([]))
    assert code == 0
    assert payload["kind"] == "evaluated"
    json.dumps(payload)


async def test_run_nothing_new_exits_1(tmp_db):
    from moonlighter.discovery.cli import _run, parse_args

    report = ScanReport(kind=ScanKind.NO_NEW_JOBS, threshold=6.5)
    with _patched(report):
        payload, code = await _run(parse_args([]))
    assert (payload["kind"], code) == ("no_new_jobs", 1)


async def test_run_unknown_source_exits_2(tmp_db):
    from moonlighter.discovery.cli import _run, parse_args

    report = ScanReport(
        kind=ScanKind.UNKNOWN_SOURCE, threshold=6.5, error="Unknown source 'lever'."
    )
    with _patched(report):
        payload, code = await _run(parse_args(["--company", "lever", "acme"]))
    assert (payload["kind"], code) == ("unknown_source", 2)
    assert payload["error"].startswith("Unknown source")


async def test_run_no_eval_passes_no_caller_to_the_service(tmp_db):
    # The whole point of --no-eval: make_caller is never even constructed.
    from moonlighter.discovery import cli
    from moonlighter.discovery.cli import _run, parse_args

    report = ScanReport(kind=ScanKind.NO_NEW_JOBS, threshold=6.5)
    scan = AsyncMock(return_value=report)
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "make_caller", side_effect=AssertionError("must not be called")),
        patch.object(cli, "scan_and_evaluate", new=scan),
    ):
        await _run(parse_args(["--no-eval"]))
    assert scan.await_args.args[-1] is None
