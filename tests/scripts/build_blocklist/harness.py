"""Shared pieces of the build_blocklist pins: the fake LLM caller, seeded rows and the main() driver."""

import itertools
import json
import re
import sys
from unittest.mock import patch

import build_blocklist
from moonlighter.core.db import Job

_URLS = itertools.count(1)


class Caller:
    """The LLM caller make_caller would build: answers by company and records every prompt."""

    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str, str]] = []

    async def __call__(self, prompt: str, model: str) -> str:
        company = re.search(r"at \*\*(.+?)\*\* were evaluated", prompt)[1]
        self.calls.append((company, prompt, model))
        answer = self.answers.get(company, [])
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, str):
            return answer
        payload = json.dumps(answer)
        # extract_json only unwraps a fence or a bare object, so a list needs the fence a model would send
        return f"```json\n{payload}\n```" if isinstance(answer, list) else payload


def scored(company: str, title: str, score: float | None, **fields) -> Job:
    defaults = {
        "source": "greenhouse",
        "url": f"https://x.test/{next(_URLS)}",
        "status": "archived",
        "score_notes": "weak fit",
    }
    return Job.create(company=company, title=title, score=score, **{**defaults, **fields})


def proposal(pattern: str, *, reasoning: str = "why", safe: object = True) -> dict[str, object]:
    return {"pattern": pattern, "examples": [pattern], "safe": safe, "reasoning": reasoning}


def run_main(monkeypatch, *flags, answers=None, profile=None, config=None, confirm=None) -> Caller:
    """Runs main(); profile None means load_profile raises FileNotFoundError, confirm None forbids input()."""
    caller = Caller(answers or {})

    def load_profile():
        if profile is None:
            raise FileNotFoundError
        return profile

    monkeypatch.setattr(sys, "argv", ["build_blocklist.py", *flags])
    monkeypatch.setattr(build_blocklist, "load_config", lambda: config or {"eval_model": "m-eval"})
    monkeypatch.setattr(build_blocklist, "load_profile", load_profile)
    monkeypatch.setattr(build_blocklist, "make_caller", lambda _config: caller)
    forbidden = AssertionError("input() must not be called")
    with patch("builtins.input", side_effect=forbidden if confirm is None else confirm):
        build_blocklist.main()
    return caller


def after_header(output: str) -> str:
    """What main() printed after its Model line and the blank line that follows it."""
    return output.split("\n\n", 1)[1]
