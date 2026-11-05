"""Shared inputs and fakes for the evaluation tests."""

import json
import logging

from moonlighter.discovery.evaluation.models import EvalInput
from moonlighter.discovery.evaluation.single import evaluate_job

MOCK_LLM_RESPONSE = json.dumps(
    {
        "score": 8.5,
        "score_notes": "Excellent match in Elixir/Phoenix. Stack aligned. Fully remote.",
        "caveats": ["Must overlap EST timezone by 4h"],
        "salary_min": 180000,
        "salary_max": 220000,
        "salary_currency": "USD",
        "salary_source": "llm_estimate",
    }
)


PROFILE = {
    "skills": [{"name": "Elixir/Phoenix", "years": 8, "level": "expert"}],
    "criteria": {
        "hard_filters": ["discard if .NET is required"],
        "soft_filters": ["preference for series A-C"],
    },
}


JOB_DESCRIPTION = "Senior Elixir Engineer. Remote. Build distributed systems with Elixir/OTP."


BLOCKLIST = ["sales", "account executive", "customer success", "marketing", "data center"]


SPEND_LIMIT_MESSAGE = "You've hit your monthly spend limit · raise it at claude.ai/settings/usage"


def make_caller(text: str):
    async def caller(prompt, model, cache_prefix=None):
        return text

    return caller


def inputs(count: int) -> list[EvalInput]:
    return [
        EvalInput(company=f"Co{index}", title=f"T{index}", description=f"d{index}")
        for index in range(count)
    ]


def recording_caller(*replies: str):
    """A caller that answers with `replies` in order (the last one repeats) and keeps every call."""
    calls: list[tuple[str, str, str | None]] = []

    async def caller(prompt, model, cache_prefix=None):
        calls.append((prompt, model, cache_prefix))
        return replies[min(len(calls), len(replies)) - 1]

    return caller, calls


async def evaluate_once(caller, *, profile=None, location=None, remote_type=None):
    return await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE if profile is None else profile,
        _caller=caller,
        location=location,
        remote_type=remote_type,
    )


def warning_records(caplog):
    return [record for record in caplog.records if record.levelno == logging.WARNING]
