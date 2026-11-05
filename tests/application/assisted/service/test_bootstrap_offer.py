"""The CV-pool bootstrap offer: made when no pool exists, never repeated after a decline or once a pool exists."""

from typing import Any

import httpx

from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion
from moonlighter.application.assisted.sheet.results import SheetKind, render_sheet_result
from moonlighter.application.assisted.sources import greenhouse as greenhouse_source
from moonlighter.core.cv_bootstrap import record_cv_bootstrap_decline
from moonlighter.core.db import init_db
from tests.application.assisted.service.fake_service import (
    bypass_cv_bootstrap_offer,
    never_extract,
    never_fetch_greenhouse,
)


async def test_prepare_application_offers_the_bootstrap_when_no_pool_exists(
    job_factory, monkeypatch, tmp_path
):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", never_fetch_greenhouse)
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")

    result = await service.prepare_application(job.id, {}, {})

    assert result.kind is SheetKind.CV_BOOTSTRAP_OFFER
    assert "bootstrap_cv_pool" in result.error
    assert "moonlighter-apply bootstrap-cv" in result.error


async def test_prepare_application_never_offers_twice_after_a_decline(
    job_factory, monkeypatch, tmp_path
):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    init_db()
    record_cv_bootstrap_decline()
    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", never_fetch_greenhouse)
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")

    result = await service.prepare_application(job.id, {}, {})

    assert result.kind is not SheetKind.CV_BOOTSTRAP_OFFER


async def test_prepare_application_never_offers_once_a_pool_exists(
    job_factory, monkeypatch, tmp_path
):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "cv-pool.yaml").write_text("experiences: []\n")
    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", never_fetch_greenhouse)
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")

    result = await service.prepare_application(job.id, {}, {})

    assert result.kind is not SheetKind.CV_BOOTSTRAP_OFFER


async def test_prepare_application_from_paste_also_offers_the_bootstrap_when_no_pool_exists(
    job_factory, monkeypatch, tmp_path
):
    # The offer is wired into BOTH public entry points (Step 4 of the brief) --
    # each is proven separately, the same discipline test_the_api_path_carries_
    # the_alias_too uses above, since a fix that reconciles only one path is
    # how the last silent regression happened.
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    monkeypatch.setattr(service, "extract_questions_from_page", never_extract)
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")

    result = await service.prepare_application_from_paste(job.id, "the whole page", {}, profile={})

    assert result.kind is SheetKind.CV_BOOTSTRAP_OFFER
    assert "bootstrap_cv_pool" in result.error
    assert "moonlighter-apply bootstrap-cv" in result.error


async def test_a_source_timeout_falls_back_to_the_paste_hint(job_factory, monkeypatch):
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/1")
    bypass_cv_bootstrap_offer()

    async def times_out(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        raise httpx.ConnectTimeout("the ATS took too long")

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", times_out)

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "prepare_application_from_paste" in out
