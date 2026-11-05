"""bootstrap_cv_pool reports what it generated or why not, and skip_cv_bootstrap records the decline."""

from moonlighter.application.cvgen.pool.bootstrap import BootstrapOutcome
from moonlighter.application.cvgen.pool.bootstrap_error import BootstrapError
from moonlighter.core.db import cv_bootstrap_declined, init_db
from moonlighter.mcp_tools import cv_pool
from tests._context import make_test_context


async def test_bootstrap_cv_pool_tool_reports_what_it_generated(monkeypatch, tmp_path):
    outcome = BootstrapOutcome(
        pool_path=tmp_path / "cv-pool.yaml",
        template_path=tmp_path / "cv-templates" / "cv-template.en.tex",
        pdf_path=tmp_path / "cv-templates" / "cv-template.en.pdf",
        bullet_count=3,
    )

    async def _fake_bootstrap(profile, config, caller, *, force=False):
        return outcome

    monkeypatch.setattr(cv_pool, "bootstrap_cv_pool_service", _fake_bootstrap)
    result = await cv_pool.bootstrap_cv_pool(context=make_test_context())
    assert "3" in result
    assert str(outcome.pool_path) in result
    assert "review" in result.lower()


async def test_bootstrap_cv_pool_tool_blames_a_missing_pdflatex_only_when_it_is_missing(
    monkeypatch, tmp_path
):
    # The original message read every None pdf_path as "pdflatex is not
    # installed" -- which sent an operator WITH pdflatex off to install it
    # while the real fault (an uncompilable document) sat in the .log beside
    # the template. Two causes, two messages.
    outcome = BootstrapOutcome(
        pool_path=tmp_path / "cv-pool.yaml",
        template_path=tmp_path / "cv-templates" / "cv-template.en.tex",
        pdf_path=None,
        bullet_count=1,
    )

    async def _fake_bootstrap(profile, config, caller, *, force=False):
        return outcome

    monkeypatch.setattr(cv_pool, "bootstrap_cv_pool_service", _fake_bootstrap)

    monkeypatch.setattr(cv_pool, "latex_available", lambda: True)
    installed = await cv_pool.bootstrap_cv_pool(context=make_test_context())
    assert "pdflatex is installed but the draft did not compile" in installed
    assert "not installed" not in installed

    monkeypatch.setattr(cv_pool, "latex_available", lambda: False)
    missing = await cv_pool.bootstrap_cv_pool(context=make_test_context())
    assert "pdflatex is not installed" in missing


async def test_bootstrap_cv_pool_tool_reports_a_bootstrap_error(monkeypatch):
    async def _fake_bootstrap(profile, config, caller, *, force=False):
        raise BootstrapError("no experience entries")

    monkeypatch.setattr(cv_pool, "bootstrap_cv_pool_service", _fake_bootstrap)
    result = await cv_pool.bootstrap_cv_pool(context=make_test_context())
    assert "no experience entries" in result


async def test_skip_cv_bootstrap_tool_records_the_decline(temporary_database):
    init_db()
    result = await cv_pool.skip_cv_bootstrap()
    assert cv_bootstrap_declined() is True
    assert "won't" in result.lower() or "never" in result.lower() or "skip" in result.lower()
