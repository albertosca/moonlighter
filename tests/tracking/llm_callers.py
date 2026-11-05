"""LLM callers for the tracking tests: canned classifications instead of a model."""

import json


def make_llm_caller(response: dict):
    """Returns an async caller that answers `response` as a JSON string."""

    async def caller(prompt, model=None):
        return json.dumps(response)

    return caller
