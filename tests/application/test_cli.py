import json
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml
from moonlighter.application import cli
from moonlighter.application.assisted.results import SheetKind, SheetResult
from moonlighter.application.cvgen.bootstrap import BootstrapOutcome
from moonlighter.core.config.errors import ConfigError


def test_parse_args_prepare_with_optional_paste():
    from moonlighter.application.cli import parse_args

    parsed_arguments = parse_args(["prepare", "42"])
    assert (parsed_arguments.command, parsed_arguments.job_id, parsed_arguments.paste) == (
        "prepare",
        42,
        None,
    )
    assert parse_args(["prepare", "42", "--paste", "-"]).paste == "-"


def test_parse_args_prepare_with_a_non_int_job_id_emits_usage_error_json_on_stdout(capsys):
    from moonlighter.application.cli import parse_args

    with pytest.raises(SystemExit) as exit_info:
        parse_args(["prepare", "not-a-number"])
    assert exit_info.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "usage_error"


async def test_run_prepare_via_api_exits_0_with_the_sheet_as_json(temporary_database):
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


async def test_run_prepare_with_paste_file_reads_it_and_uses_the_paste_path(
    temporary_database, tmp_path
):
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


async def test_run_prepare_with_paste_dash_reads_stdin(temporary_database, monkeypatch):
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


async def test_run_prepare_job_not_found_exits_1(temporary_database):
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


def test_run_via_run_classifies_a_missing_paste_file_as_a_usage_error(temporary_database, capsys):
    # Measured: moonlighter-apply prepare 1 --paste /nonexistent lands on exit
    # 3 (FileNotFoundError) today. A bad --paste path is a bad argument, not
    # a crash -- exit 2, kind "usage_error". Goes THROUGH run() with the real
    # module tuple, per the review brief.
    from moonlighter.application import cli
    from moonlighter.core.cli import run

    with patch.object(cli, "bootstrap", return_value=({}, {})):
        parsed_arguments = cli.parse_args(["prepare", "42", "--paste", "/nonexistent/file"])
        code = run(lambda: cli._run(parsed_arguments), usage=cli.USAGE_ERRORS)
    assert code == 2
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "usage_error"
    assert out["type"] == "FileNotFoundError"


async def test_run_prepare_with_url_ingests_then_prepares(temporary_database):
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


async def test_run_prepare_with_an_unreadable_url_exits_1_with_its_own_kind(temporary_database):
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
        with pytest.raises(SystemExit) as exit_info:
            parse_args(argv)
        assert exit_info.value.code == 2
        assert json.loads(capsys.readouterr().out)["kind"] == "usage_error"


def test_parse_args_prepare_with_url_and_company_title_overrides():
    from moonlighter.application.cli import parse_args

    parsed_arguments = parse_args(["prepare", "--url", "u", "--company", "Acme", "--title", "Eng"])
    assert (parsed_arguments.url, parsed_arguments.company, parsed_arguments.title) == (
        "u",
        "Acme",
        "Eng",
    )


def test_parse_args_prepare_company_or_title_without_url_is_a_usage_error(capsys):
    import json

    from moonlighter.application.cli import parse_args

    for argv in (
        ["prepare", "42", "--company", "Acme"],
        ["prepare", "42", "--title", "Eng"],
    ):
        with pytest.raises(SystemExit) as exit_info:
            parse_args(argv)
        assert exit_info.value.code == 2
        assert json.loads(capsys.readouterr().out)["kind"] == "usage_error"


async def test_run_prepare_with_url_passes_company_and_title_through(temporary_database):
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


async def test_apply_doctor_returns_the_doctor_payload(temporary_database):
    from moonlighter.application import cli

    with patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)):
        payload, code = await cli._run(cli.parse_args(["doctor"]))
    assert (payload, code) == ({"kind": "doctor"}, 0)


async def test_apply_doctor_stays_offline_without_the_flag(temporary_database):
    from moonlighter.application import cli

    report = AsyncMock()
    with (
        patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(cli, "link_report", report),
    ):
        payload, _ = await cli._run(cli.parse_args(["doctor"]))
    report.assert_not_awaited()
    assert "links" not in payload


async def test_apply_doctor_online_reports_the_cv_links_and_fails_on_a_broken_one(
    temporary_database,
):
    from moonlighter.application import cli

    links = [
        {"url": "https://github.com/albertosca", "status": 200, "ok": True, "note": None},
        {"url": "https://github.com/albertoalbuquerque", "status": 404, "ok": False, "note": None},
    ]
    with (
        patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(cli, "link_report", AsyncMock(return_value=links)),
    ):
        payload, code = await cli._run(cli.parse_args(["doctor", "--online"]))
    assert payload["links"] == links
    assert code == 1


async def test_apply_doctor_online_keeps_exit_0_when_links_are_fine_or_unverified(
    temporary_database,
):
    from moonlighter.application import cli

    links = [{"url": "https://www.linkedin.com/in/x", "status": 999, "ok": None, "note": "n"}]
    with (
        patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(cli, "link_report", AsyncMock(return_value=links)),
    ):
        _, code = await cli._run(cli.parse_args(["doctor", "--online"]))
    assert code == 0


def test_apply_help_carries_the_slice_epilog(capsys):
    from moonlighter.application.cli import parse_args

    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--help"])
    assert exit_info.value.code == 0
    assert "installed:" in capsys.readouterr().out


async def test_bootstrap_cv_subcommand_reports_what_it_generated(monkeypatch, tmp_path):
    from moonlighter.application import cli
    from moonlighter.application.cvgen.bootstrap import BootstrapOutcome

    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))
    outcome = BootstrapOutcome(
        pool_path=tmp_path / "cv-pool.yaml",
        template_path=tmp_path / "cv-templates" / "cv-template.en.tex",
        pdf_path=None,
        bullet_count=2,
    )

    async def _fake_bootstrap(profile, config, caller, *, force=False):
        return outcome

    monkeypatch.setattr(cli, "bootstrap_cv_pool", _fake_bootstrap)
    payload, code = await cli._run(cli.parse_args(["bootstrap-cv"]))
    assert code == 0
    assert payload["bullet_count"] == 2
    assert payload["pool_path"] == str(outcome.pool_path)


async def test_bootstrap_cv_subcommand_threads_the_force_flag(monkeypatch, tmp_path):
    from moonlighter.application import cli
    from moonlighter.application.cvgen.bootstrap import BootstrapOutcome

    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))
    received: dict[str, object] = {}

    async def _fake_bootstrap(profile, config, caller, *, force=False):
        received["force"] = force
        return BootstrapOutcome(tmp_path / "p.yaml", tmp_path / "t.tex", None, 1)

    monkeypatch.setattr(cli, "bootstrap_cv_pool", _fake_bootstrap)
    await cli._run(cli.parse_args(["bootstrap-cv", "--force"]))
    assert received["force"] is True


def test_bootstrap_cv_subcommand_reports_a_bootstrap_error_as_expected_failure(monkeypatch, capsys):
    # _run() itself never classifies its own exceptions -- that's run()'s job
    # (see core/cli.py's docstring and this slice's other expected/usage-error
    # test, test_run_via_run_classifies_a_missing_paste_file_as_a_usage_error,
    # a few tests up), so this goes THROUGH run() with EXPECTED_ERRORS, same
    # as that sibling test does for USAGE_ERRORS -- not through a bare
    # `await cli._run(...)`, which would let the BootstrapError propagate
    # uncaught instead of returning a (payload, code) tuple.
    from moonlighter.application import cli
    from moonlighter.application.cvgen.bootstrap_error import BootstrapError
    from moonlighter.core.cli import run

    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))

    async def _fake_bootstrap(profile, config, caller, *, force=False):
        raise BootstrapError("a pool already exists")

    monkeypatch.setattr(cli, "bootstrap_cv_pool", _fake_bootstrap)
    parsed_arguments = cli.parse_args(["bootstrap-cv"])
    code = run(lambda: cli._run(parsed_arguments), expected=cli.EXPECTED_ERRORS)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "expected_failure"


async def test_bootstrap_cv_skip_records_the_decline_without_calling_the_llm(
    monkeypatch, temporary_database
):
    from moonlighter.application import cli
    from moonlighter.core.db import cv_bootstrap_declined, init_db

    init_db()
    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))
    monkeypatch.setattr(
        cli,
        "bootstrap_cv_pool",
        lambda *positional_arguments, **keyword_arguments: (_ for _ in ()).throw(
            AssertionError("must not draft when --skip is given")
        ),
    )
    _payload, code = await cli._run(cli.parse_args(["bootstrap-cv", "--skip"]))
    assert code == 0
    assert cv_bootstrap_declined() is True


async def test_apply_doctor_online_reports_a_broken_config_instead_of_crashing(
    temporary_database,
):
    """--online exists to diagnose; a config that does not load must come back in
    the payload the way plain doctor reports it, not as a crash (exit 3)."""
    import yaml
    from moonlighter.application import cli

    report = AsyncMock()
    with (
        patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 1)),
        patch.object(cli, "load_config", side_effect=yaml.YAMLError("bad yaml")),
        patch.object(cli, "link_report", report),
    ):
        payload, code = await cli._run(cli.parse_args(["doctor", "--online"]))
    report.assert_not_awaited()
    assert payload["links"] is None
    assert "bad yaml" in payload["links_error"]
    assert code == 1


async def test_apply_doctor_online_says_when_there_was_nothing_to_check(temporary_database):
    """An empty list read the same as "every link works" (2026-09-29 review)."""
    from moonlighter.application import cli

    with (
        patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(cli, "link_report", AsyncMock(return_value=[])),
    ):
        payload, code = await cli._run(cli.parse_args(["doctor", "--online"]))
    assert payload["links"] == []
    assert "no CV template" in payload["links_note"]
    assert code == 0


def test_parse_args_usage_errors_carry_the_message_the_operator_reads(capsys):
    expectations = (
        (["prepare"], "prepare takes exactly one of JOB_ID or --url"),
        (["prepare", "42", "--url", "https://x"], "prepare takes exactly one of JOB_ID or --url"),
        (
            ["prepare", "42", "--company", "Acme"],
            "--company and --title are only meaningful with --url",
        ),
        (
            ["prepare", "42", "--title", "Eng"],
            "--company and --title are only meaningful with --url",
        ),
    )
    for argv, message in expectations:
        with pytest.raises(SystemExit):
            cli.parse_args(argv)
        payload = json.loads(capsys.readouterr().out)
        assert payload == {"kind": "usage_error", "error": message}


def test_parse_args_reads_sys_argv_when_given_no_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["moonlighter-apply", "doctor", "--online"])
    parsed_arguments = cli.parse_args()
    assert (parsed_arguments.command, parsed_arguments.online) == ("doctor", True)


@pytest.mark.parametrize(
    "failure", [ConfigError("bad config"), OSError("bad disk"), yaml.YAMLError("bad yaml")]
)
async def test_apply_doctor_online_reports_every_load_failure_with_the_same_prefix(
    temporary_database, failure
):
    with (
        patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 1)),
        patch.object(cli, "load_config", side_effect=failure),
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
        patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(cli, "link_report", AsyncMock(return_value=[])),
    ):
        payload, _ = await cli._run(cli.parse_args(["doctor", "--online"]))
    assert payload["links_note"] == (
        "no CV template with header links found in cv.template_dir; nothing checked"
    )


async def test_apply_doctor_never_calls_bootstrap_even_online(temporary_database):
    with (
        patch.object(cli, "bootstrap") as bootstrap_spy,
        patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(cli, "link_report", AsyncMock(return_value=[])),
    ):
        await cli._run(cli.parse_args(["doctor"]))
        await cli._run(cli.parse_args(["doctor", "--online"]))
    bootstrap_spy.assert_not_called()


async def test_bootstrap_cv_subcommand_payload_has_exactly_these_keys_and_values(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))
    outcome = BootstrapOutcome(
        pool_path=tmp_path / "cv-pool.yaml",
        template_path=tmp_path / "cv-templates" / "cv-template.en.tex",
        pdf_path=tmp_path / "sample.pdf",
        bullet_count=3,
    )

    async def _fake_bootstrap(profile, config, caller, *, force=False):
        return outcome

    monkeypatch.setattr(cli, "bootstrap_cv_pool", _fake_bootstrap)
    payload, code = await cli._run(cli.parse_args(["bootstrap-cv"]))
    assert code == 0
    assert payload == {
        "kind": "cv_bootstrap",
        "pool_path": str(tmp_path / "cv-pool.yaml"),
        "template_path": str(tmp_path / "cv-templates" / "cv-template.en.tex"),
        "pdf_path": str(tmp_path / "sample.pdf"),
        "bullet_count": 3,
    }


async def test_bootstrap_cv_subcommand_hands_over_profile_config_and_the_caller_in_order(
    monkeypatch, tmp_path
):
    config, profile, caller = {"config": 1}, {"profile": 2}, object()
    monkeypatch.setattr(cli, "bootstrap", lambda: (config, profile))
    caller_factory = Mock(return_value=caller)
    monkeypatch.setattr(cli, "make_caller", caller_factory)
    drafter = AsyncMock(
        return_value=BootstrapOutcome(tmp_path / "p.yaml", tmp_path / "t.tex", None, 1)
    )
    monkeypatch.setattr(cli, "bootstrap_cv_pool", drafter)
    await cli._run(cli.parse_args(["bootstrap-cv"]))
    caller_factory.assert_called_once_with(config)
    drafter.assert_awaited_once_with(profile, config, caller, force=False)


async def test_bootstrap_cv_skip_payload_is_exactly_the_skipped_kind(
    monkeypatch, temporary_database
):
    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))
    payload, code = await cli._run(cli.parse_args(["bootstrap-cv", "--skip"]))
    assert (payload, code) == ({"kind": "cv_bootstrap_skipped"}, 0)


async def test_run_prepare_hands_over_job_id_config_and_profile_in_order(temporary_database):
    config, profile = {"config": 1}, {"profile": 2}
    result = SheetResult(
        kind=SheetKind.SHEET, composed=[], job_title="T", company="C", apply_url="u"
    )
    prepare = AsyncMock(return_value=result)
    with (
        patch.object(cli, "bootstrap", return_value=(config, profile)),
        patch.object(cli, "prepare_application", new=prepare),
    ):
        await cli._run(cli.parse_args(["prepare", "42"]))
    prepare.assert_awaited_once_with(42, config, profile)


async def test_run_prepare_with_paste_hands_over_text_config_and_profile_by_keyword(
    temporary_database, tmp_path
):
    config, profile = {"config": 1}, {"profile": 2}
    page = tmp_path / "page.txt"
    page.write_text("Full name")
    result = SheetResult(
        kind=SheetKind.SHEET, composed=[], job_title="T", company="C", apply_url="u"
    )
    paste = AsyncMock(return_value=result)
    with (
        patch.object(cli, "bootstrap", return_value=(config, profile)),
        patch.object(cli, "prepare_application_from_paste", new=paste),
    ):
        await cli._run(cli.parse_args(["prepare", "42", "--paste", str(page)]))
    paste.assert_awaited_once_with(42, "Full name", config, profile=profile)
