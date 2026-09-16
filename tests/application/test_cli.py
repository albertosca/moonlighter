import json
from unittest.mock import AsyncMock, patch

import pytest
from moonlighter.application.assisted.results import SheetKind, SheetResult


def test_parse_args_prepare_with_optional_paste():
    from moonlighter.application.cli import parse_args

    args = parse_args(["prepare", "42"])
    assert (args.command, args.job_id, args.paste) == ("prepare", 42, None)
    assert parse_args(["prepare", "42", "--paste", "-"]).paste == "-"


def test_parse_args_prepare_with_a_non_int_job_id_emits_usage_error_json_on_stdout(capsys):
    from moonlighter.application.cli import parse_args

    with pytest.raises(SystemExit) as exc:
        parse_args(["prepare", "not-a-number"])
    assert exc.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "usage_error"


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


def test_run_via_run_classifies_a_missing_paste_file_as_a_usage_error(tmp_db, capsys):
    # Measured: moonlighter-apply prepare 1 --paste /nonexistent lands on exit
    # 3 (FileNotFoundError) today. A bad --paste path is a bad argument, not
    # a crash -- exit 2, kind "usage_error". Goes THROUGH run() with the real
    # module tuple, per the review brief.
    from moonlighter.application import cli
    from moonlighter.core.cli import run

    with patch.object(cli, "bootstrap", return_value=({}, {})):
        args = cli.parse_args(["prepare", "42", "--paste", "/nonexistent/file"])
        code = run(lambda: cli._run(args), usage=cli.USAGE_ERRORS)
    assert code == 2
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "usage_error"
    assert out["type"] == "FileNotFoundError"


async def test_run_prepare_with_url_ingests_then_prepares(tmp_db):
    from moonlighter.application import cli
    from moonlighter.core.db import Job, init_db

    init_db()
    job = Job.create(
        source="manual", company="Acme", title="Eng", url="https://x/1", status="needs_review"
    )
    result = SheetResult(
        kind=SheetKind.SHEET, composed=[], job_title="Eng", company="Acme", apply_url="https://x/1"
    )
    prepare = AsyncMock(return_value=result)
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "job_from_url", new=AsyncMock(return_value=job)),
        patch.object(cli, "prepare_application", new=prepare),
    ):
        payload, code = await cli._run(cli.parse_args(["prepare", "--url", "https://x/1"]))
    assert (payload["kind"], code) == ("sheet", 0)
    assert prepare.await_args.args[0] == job.id


async def test_run_prepare_with_an_unreadable_url_exits_1_with_its_own_kind(tmp_db):
    from moonlighter.application import cli

    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "job_from_url", new=AsyncMock(return_value=None)),
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


def test_parse_args_prepare_requires_exactly_one_of_job_id_and_url(capsys):
    import json

    from moonlighter.application.cli import parse_args

    for argv in (["prepare"], ["prepare", "42", "--url", "https://x"]):
        with pytest.raises(SystemExit) as exc:
            parse_args(argv)
        assert exc.value.code == 2
        assert json.loads(capsys.readouterr().out)["kind"] == "usage_error"


def test_parse_args_prepare_with_url_and_company_title_overrides():
    from moonlighter.application.cli import parse_args

    args = parse_args(["prepare", "--url", "u", "--company", "Acme", "--title", "Eng"])
    assert (args.url, args.company, args.title) == ("u", "Acme", "Eng")


def test_parse_args_prepare_company_or_title_without_url_is_a_usage_error(capsys):
    import json

    from moonlighter.application.cli import parse_args

    for argv in (
        ["prepare", "42", "--company", "Acme"],
        ["prepare", "42", "--title", "Eng"],
    ):
        with pytest.raises(SystemExit) as exc:
            parse_args(argv)
        assert exc.value.code == 2
        assert json.loads(capsys.readouterr().out)["kind"] == "usage_error"


async def test_run_prepare_with_url_passes_company_and_title_through(tmp_db):
    from moonlighter.application import cli
    from moonlighter.core.db import Job, init_db

    init_db()
    job = Job.create(
        source="manual", company="Acme", title="Eng", url="https://x/1", status="needs_review"
    )
    result = SheetResult(
        kind=SheetKind.SHEET, composed=[], job_title="Eng", company="Acme", apply_url="https://x/1"
    )
    ingest = AsyncMock(return_value=job)
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "job_from_url", new=ingest),
        patch.object(cli, "prepare_application", new=AsyncMock(return_value=result)),
    ):
        await cli._run(
            cli.parse_args(
                ["prepare", "--url", "https://x/1", "--company", "Acme", "--title", "Eng"]
            )
        )
    assert ingest.await_args.kwargs == {"company": "Acme", "title": "Eng"}


def test_apply_keeps_its_grammar_and_gains_doctor():
    from moonlighter.application.cli import parse_args

    assert parse_args(["doctor"]).command == "doctor"
    assert parse_args(["prepare", "42"]).command == "prepare"


async def test_apply_doctor_returns_the_doctor_payload(tmp_db):
    from moonlighter.application import cli

    with patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)):
        payload, code = await cli._run(cli.parse_args(["doctor"]))
    assert (payload, code) == ({"kind": "doctor"}, 0)


def test_apply_help_carries_the_slice_epilog(capsys):
    from moonlighter.application.cli import parse_args

    with pytest.raises(SystemExit) as exc:
        parse_args(["--help"])
    assert exc.value.code == 0
    assert "installed:" in capsys.readouterr().out
