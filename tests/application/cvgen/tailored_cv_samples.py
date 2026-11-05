"""Shared inputs for the tests that run a whole tailored-CV generation."""

import json
from pathlib import Path
from typing import Any

POOL_YAML = """
experiences:
  - company: Trybe
    title: Dev
    period: "2023 -- 2026"
    location: BH
    bullets:
      - id: t-a
        angles: [backend]
        latex: 'Did A'
"""
TWO_BULLET_POOL_YAML = """
experiences:
  - company: Trybe
    title: Dev
    period: "2023 -- 2026"
    location: BH
    bullets:
      - id: t-a
        angles: [backend]
        latex: 'Did A'
      - id: t-b
        angles: [backend]
        latex: 'Did B'
"""
TEMPLATE = (
    "%%BASE_SUMMARY: The base summary line\n"
    "%%BASE_EXPERTISE: Elixir, React\n"
    "\\cvlistitem{%%SUMMARY%%}\n\\cvlistitem{%%TECHNICAL_EXPERTISE%%}\n"
    "%%EXPERIENCE%%\n%%OPEN_SOURCE%%\n"
)
JOB = {"id": 42, "title": "Eng", "company": "acme", "description": "d"}
GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["t-a"],
        "open_source": [],
    }
)
GENERATE_TWO_BULLETS = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["t-a", "t-b"],
        "open_source": [],
    }
)
GENERATE_PORTUGUESE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "pt",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["t-a"],
        "open_source": [],
    }
)


def write_pool(config: dict[str, Any], pool_yaml: str) -> None:
    """Replace the pool file a `config` fixture points at.

    Synchronous on purpose: the async tests that call it would otherwise do a
    blocking `Path.write_text` inside the event loop, which ASYNC240 rejects.
    """
    Path(config["cv"]["pool"]).write_text(pool_yaml)


def counting_caller(response: str = GENERATE):
    """A model stand-in returning `response`, with the number of calls it took."""
    calls = {"n": 0}

    async def call(prompt, model, cache_prefix=None):
        calls["n"] += 1
        return response

    return call, calls


def fixed_caller(response: str):
    """A model stand-in that returns `response` and counts nothing."""

    async def call(prompt, model, cache_prefix=None):
        return response

    return call
