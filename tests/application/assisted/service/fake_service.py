"""Fakes the assisted-service tests share: sources and models that must not be reached, and a canned caller."""

from typing import Any

from moonlighter.application.assisted.questions import FormQuestion
from moonlighter.core.cv_bootstrap import record_cv_bootstrap_decline


def never_fetch_greenhouse(board: str, job_id: str, client: Any) -> Any:
    raise AssertionError("greenhouse API must not be called for this job")


def never_fetch_recruitee(slug: str, offer: str, client: Any) -> Any:
    raise AssertionError("recruitee API must not be called for this job")


async def never_llm(prompt: str, model: str, cache_prefix: str | None = None) -> str:
    raise AssertionError("the LLM must not be consulted when no questions were found")


def stub_caller(answer: str = "a generated answer") -> Any:
    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return answer

    return _call


def bypass_cv_bootstrap_offer() -> None:
    """Make the CV-pool bootstrap offer a no-op so a test exercises routing or caching, not the offer.

    Recording a decline keeps the offer quiet without touching resolved_pool_path, so
    ensure_tailored_cv's own no-pool branch (and every monkeypatch of it) sees the
    "no pool" world. Needs the DB schema to exist, which job_factory's setup guarantees.
    """
    record_cv_bootstrap_decline()


async def never_extract(page_text: str, llm_caller: Any) -> list[FormQuestion]:
    """An extraction that fails the test if it runs."""
    raise AssertionError("must not extract questions when the job does not exist")
