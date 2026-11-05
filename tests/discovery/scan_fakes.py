"""Fakes shared by the scan tests: config, an evaluation, raw jobs and a whole-scan runner."""

from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.discovery.evaluation.models import EvaluationResult
from moonlighter.discovery.results import render_scan_report
from moonlighter.discovery.scanning import scan_and_evaluate
from moonlighter.discovery.sources.base import RawJob

CONFIG = {
    "score_threshold": 7.0,
    "llm_model": "claude-haiku-4-5-20251001",
    "title_blocklist": ["staff accountant"],
}


PROFILE: dict = {}


HOME_BH: dict = {"criteria": {"home_city": "Belo Horizonte"}}


def evaluation_result(score=8.0, caveats=None):
    return EvaluationResult(
        score=score,
        score_notes="match",
        caveats=caveats or [],
        salary_min=150000,
        salary_max=200000,
        salary_currency="USD",
        salary_source="llm_estimate",
    )


def make_raw_job(index, title="Engineer", source="greenhouse"):
    return RawJob(
        source=source,
        company=f"Co{index}",
        title=title,
        url=f"https://x.com/scan/{index}",
        description="A detailed job description that goes on.",
    )


class FakeBrowserScanner:
    """Stands in for a registered moonlighter.scanners plugin (LinkedIn is the
    real-world example, provided by the private moonlighter-linkedin package --
    see docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md).
    run_scan configures its scan() return/raise per test via closure."""

    _raised_error: Exception | None = None
    _jobs: ClassVar[list] = []

    def __init__(self, page):
        pass

    async def scan(self, **keyword_arguments):
        if self._raised_error is not None:
            raise self._raised_error
        return self._jobs


async def run_scan(  # noqa: PLR0913 - every knob a scan test turns, all keyword-only
    raws, *, eval_mock=None, linkedin_error=None, linkedin_jobs=None, config=None, profile=None
):
    """Runs scan_and_evaluate with mocked HTTP scanners serving `raws`.

    linkedin_error: the exception the registered browser-scanner plugin's scan()
    should raise. linkedin_jobs: the list of RawJob it should return instead.
    If both are None, no browser-scanner plugin is registered at all (the
    steady state for the public repo alone).

    eval_mock: an AsyncMock applied per job within the batch. Can be
    AsyncMock(return_value=EvaluationResult) or AsyncMock(side_effect=exc).
    """
    resolved_config = config or {**CONFIG, "title_blocklist": ["staff accountant"]}
    _eval_per_job = eval_mock or AsyncMock(return_value=evaluation_result(8.0))

    async def _batch(jobs, profile, model, *, caller):
        # Applies eval_mock to each job in the batch; errors propagate to the batch handler in `_score`, which releases the claims.
        return [await _eval_per_job(job.company, model) for job in jobs]

    registered = []
    if linkedin_error is not None or linkedin_jobs is not None:
        FakeBrowserScanner._raised_error = linkedin_error
        FakeBrowserScanner._jobs = linkedin_jobs or []
        registered = [FakeBrowserScanner]

    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.pipeline.evaluate_jobs_batch", new=_batch),
        patch("moonlighter.discovery.collection.discover_entry_points", return_value=registered),
        patch(
            "moonlighter.discovery.scanning.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=raws)
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(return_value=AsyncMock())
        report = await scan_and_evaluate(
            "", "all", resolved_config, profile if profile is not None else PROFILE, MagicMock()
        )
        return render_scan_report(report)


def store_config(**overrides):
    return {"score_threshold": 6.5, "title_blocklist": [], **overrides}


class BatchRecorder:
    """Stands in for evaluate_jobs_batch: records each call and scores every job 8.0."""

    def __init__(self):
        self.sizes = []
        self.models = []

    async def __call__(self, jobs, profile, model, *, caller):
        self.sizes.append(len(jobs))
        self.models.append(model)
        return [evaluation_result(8.0) for _ in jobs]
