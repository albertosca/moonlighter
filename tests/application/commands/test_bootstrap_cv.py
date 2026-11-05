"""The bootstrap-cv subcommand: the payload it reports, what it hands the drafter, --force and --skip."""

from unittest.mock import AsyncMock, Mock

from moonlighter.application import cli
from moonlighter.application.commands import bootstrap_cv as bootstrap_cv_command
from moonlighter.application.cvgen.bootstrap import BootstrapOutcome
from moonlighter.core.db import cv_bootstrap_declined, init_db


async def test_bootstrap_cv_subcommand_reports_what_it_generated(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))
    outcome = BootstrapOutcome(
        pool_path=tmp_path / "cv-pool.yaml",
        template_path=tmp_path / "cv-templates" / "cv-template.en.tex",
        pdf_path=None,
        bullet_count=2,
    )

    async def _fake_bootstrap(profile, config, caller, *, force=False):
        return outcome

    monkeypatch.setattr(bootstrap_cv_command, "bootstrap_cv_pool", _fake_bootstrap)
    payload, code = await cli._run(cli.parse_args(["bootstrap-cv"]))
    assert code == 0
    assert payload["bullet_count"] == 2
    assert payload["pool_path"] == str(outcome.pool_path)


async def test_bootstrap_cv_subcommand_threads_the_force_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))
    received: dict[str, object] = {}

    async def _fake_bootstrap(profile, config, caller, *, force=False):
        received["force"] = force
        return BootstrapOutcome(tmp_path / "p.yaml", tmp_path / "t.tex", None, 1)

    monkeypatch.setattr(bootstrap_cv_command, "bootstrap_cv_pool", _fake_bootstrap)
    await cli._run(cli.parse_args(["bootstrap-cv", "--force"]))
    assert received["force"] is True


async def test_bootstrap_cv_skip_records_the_decline_without_calling_the_llm(
    monkeypatch, temporary_database
):
    init_db()
    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))
    monkeypatch.setattr(
        bootstrap_cv_command,
        "bootstrap_cv_pool",
        lambda *positional_arguments, **keyword_arguments: (_ for _ in ()).throw(
            AssertionError("must not draft when --skip is given")
        ),
    )
    _payload, code = await cli._run(cli.parse_args(["bootstrap-cv", "--skip"]))
    assert code == 0
    assert cv_bootstrap_declined() is True


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

    monkeypatch.setattr(bootstrap_cv_command, "bootstrap_cv_pool", _fake_bootstrap)
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
    monkeypatch.setattr(bootstrap_cv_command, "make_caller", caller_factory)
    drafter = AsyncMock(
        return_value=BootstrapOutcome(tmp_path / "p.yaml", tmp_path / "t.tex", None, 1)
    )
    monkeypatch.setattr(bootstrap_cv_command, "bootstrap_cv_pool", drafter)
    await cli._run(cli.parse_args(["bootstrap-cv"]))
    caller_factory.assert_called_once_with(config)
    drafter.assert_awaited_once_with(profile, config, caller, force=False)


async def test_bootstrap_cv_skip_payload_is_exactly_the_skipped_kind(
    monkeypatch, temporary_database
):
    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))
    payload, code = await cli._run(cli.parse_args(["bootstrap-cv", "--skip"]))
    assert (payload, code) == ({"kind": "cv_bootstrap_skipped"}, 0)
