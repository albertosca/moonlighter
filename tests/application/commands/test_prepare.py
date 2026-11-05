"""The prepare subcommand: ingesting a URL, reading the paste, what it hands the composer, its exit code."""

import io
import json
from unittest.mock import AsyncMock, patch

from moonlighter.application import cli
from moonlighter.application.assisted.sheet.results import SheetKind, SheetResult
from moonlighter.application.commands import prepare as prepare_command
from moonlighter.core.db import Job, init_db


def _sheet_result(
    *,
    kind=SheetKind.SHEET,
    job_title="T",
    company="C",
    apply_url="u",
    error=None,
):
    return SheetResult(
        kind=kind,
        composed=[],
        job_title=job_title,
        company=company,
        apply_url=apply_url,
        error=error,
    )


async def test_run_prepare_via_api_exits_0_with_the_sheet_as_json(temporary_database):
    result = _sheet_result()
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(prepare_command, "prepare_application", new=AsyncMock(return_value=result)),
    ):
        payload, code = await cli._run(cli.parse_args(["prepare", "42"]))
    assert (payload["kind"], code) == ("sheet", 0)
    json.dumps(payload)


async def test_run_prepare_with_paste_file_reads_it_and_uses_the_paste_path(
    temporary_database, tmp_path
):
    page = tmp_path / "page.txt"
    page.write_text("Full name\nEmail")
    paste = AsyncMock(return_value=_sheet_result())
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(prepare_command, "prepare_application_from_paste", new=paste),
    ):
        _payload, code = await cli._run(cli.parse_args(["prepare", "42", "--paste", str(page)]))
    assert code == 0
    assert paste.await_args.args[1] == "Full name\nEmail"


async def test_run_prepare_with_paste_dash_reads_stdin(temporary_database, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("pasted page"))
    paste = AsyncMock(return_value=_sheet_result())
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(prepare_command, "prepare_application_from_paste", new=paste),
    ):
        await cli._run(cli.parse_args(["prepare", "42", "--paste", "-"]))
    assert paste.await_args.args[1] == "pasted page"


async def test_run_prepare_job_not_found_exits_1(temporary_database):
    result = _sheet_result(
        kind=SheetKind.JOB_NOT_FOUND,
        job_title="",
        company="",
        apply_url="",
        error="Job 42 not found.",
    )
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(prepare_command, "prepare_application", new=AsyncMock(return_value=result)),
    ):
        payload, code = await cli._run(cli.parse_args(["prepare", "42"]))
    assert (payload["kind"], payload["error"], code) == ("job_not_found", "Job 42 not found.", 1)


async def test_run_prepare_with_url_ingests_then_prepares(temporary_database):
    init_db()
    job = Job.create(
        source="manual", company="Acme", title="Eng", url="https://x/1", status="needs_review"
    )
    result = _sheet_result(job_title="Eng", company="Acme", apply_url="https://x/1")
    prepare = AsyncMock(return_value=result)
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(prepare_command, "job_from_url", new=AsyncMock(return_value=job)),
        patch.object(prepare_command, "prepare_application", new=prepare),
    ):
        payload, code = await cli._run(cli.parse_args(["prepare", "--url", "https://x/1"]))
    assert (payload["kind"], code) == ("sheet", 0)
    assert prepare.await_args.args[0] == job.id


async def test_run_prepare_with_an_unreadable_url_exits_1_with_its_own_kind(temporary_database):
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(prepare_command, "job_from_url", new=AsyncMock(return_value=None)),
    ):
        payload, code = await cli._run(
            cli.parse_args(["prepare", "--url", "https://example.com/x"])
        )
    assert (payload["kind"], code) == ("posting_unreadable", 1)
    assert payload["apply_url"] == "https://example.com/x"
    assert payload["error"] == (
        "The posting at https://example.com/x is not on a known ATS or could not be read. "
        "Pass --company and --title to ingest it anyway, or give a job id."
    )


async def test_run_prepare_with_url_passes_company_and_title_through(temporary_database):
    init_db()
    job = Job.create(
        source="manual", company="Acme", title="Eng", url="https://x/1", status="needs_review"
    )
    result = _sheet_result(job_title="Eng", company="Acme", apply_url="https://x/1")
    ingest = AsyncMock(return_value=job)
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(prepare_command, "job_from_url", new=ingest),
        patch.object(prepare_command, "prepare_application", new=AsyncMock(return_value=result)),
    ):
        await cli._run(
            cli.parse_args(
                ["prepare", "--url", "https://x/1", "--company", "Acme", "--title", "Eng"]
            )
        )
    assert ingest.await_args.kwargs == {"company": "Acme", "title": "Eng"}


async def test_run_prepare_hands_over_job_id_config_and_profile_in_order(temporary_database):
    config, profile = {"config": 1}, {"profile": 2}
    prepare = AsyncMock(return_value=_sheet_result())
    with (
        patch.object(cli, "bootstrap", return_value=(config, profile)),
        patch.object(prepare_command, "prepare_application", new=prepare),
    ):
        await cli._run(cli.parse_args(["prepare", "42"]))
    prepare.assert_awaited_once_with(42, config, profile)


async def test_run_prepare_with_paste_hands_over_text_config_and_profile_by_keyword(
    temporary_database, tmp_path
):
    config, profile = {"config": 1}, {"profile": 2}
    page = tmp_path / "page.txt"
    page.write_text("Full name")
    paste = AsyncMock(return_value=_sheet_result())
    with (
        patch.object(cli, "bootstrap", return_value=(config, profile)),
        patch.object(prepare_command, "prepare_application_from_paste", new=paste),
    ):
        await cli._run(cli.parse_args(["prepare", "42", "--paste", str(page)]))
    paste.assert_awaited_once_with(42, "Full name", config, profile=profile)
