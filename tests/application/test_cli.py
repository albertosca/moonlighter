import json
from unittest.mock import AsyncMock, patch

from moonlighter.application.assisted.results import SheetKind, SheetResult


def test_parse_args_prepare_with_optional_paste():
    from moonlighter.application.cli import parse_args

    args = parse_args(["prepare", "42"])
    assert (args.command, args.job_id, args.paste) == ("prepare", 42, None)
    assert parse_args(["prepare", "42", "--paste", "-"]).paste == "-"


async def test_run_prepare_via_api_exits_0_with_the_sheet_as_json(tmp_db):
    from moonlighter.application import cli

    result = SheetResult(
        kind=SheetKind.SHEET, composed=[], job_title="T", company="C", apply_url="u"
    )
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "prepare_application", new=AsyncMock(return_value=result)),
    ):
        payload, code = await cli._run(cli.parse_args(["prepare", "42"]))
    assert (payload["kind"], code) == ("sheet", 0)
    json.dumps(payload)


async def test_run_prepare_with_paste_file_reads_it_and_uses_the_paste_path(tmp_db, tmp_path):
    from moonlighter.application import cli

    page = tmp_path / "page.txt"
    page.write_text("Full name\nEmail")
    result = SheetResult(
        kind=SheetKind.SHEET, composed=[], job_title="T", company="C", apply_url="u"
    )
    paste = AsyncMock(return_value=result)
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "prepare_application_from_paste", new=paste),
    ):
        _payload, code = await cli._run(cli.parse_args(["prepare", "42", "--paste", str(page)]))
    assert code == 0
    assert paste.await_args.args[1] == "Full name\nEmail"


async def test_run_prepare_with_paste_dash_reads_stdin(tmp_db, monkeypatch):
    import io

    from moonlighter.application import cli

    monkeypatch.setattr("sys.stdin", io.StringIO("pasted page"))
    result = SheetResult(
        kind=SheetKind.SHEET, composed=[], job_title="T", company="C", apply_url="u"
    )
    paste = AsyncMock(return_value=result)
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "prepare_application_from_paste", new=paste),
    ):
        await cli._run(cli.parse_args(["prepare", "42", "--paste", "-"]))
    assert paste.await_args.args[1] == "pasted page"


async def test_run_prepare_job_not_found_exits_1(tmp_db):
    from moonlighter.application import cli

    result = SheetResult(
        kind=SheetKind.JOB_NOT_FOUND,
        composed=[],
        job_title="",
        company="",
        apply_url="",
        error="Job 42 not found.",
    )
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "prepare_application", new=AsyncMock(return_value=result)),
    ):
        payload, code = await cli._run(cli.parse_args(["prepare", "42"]))
    assert (payload["kind"], payload["error"], code) == ("job_not_found", "Job 42 not found.", 1)
