"""The pasted-page fixture and a fake model that records the prompt it was given."""

from tests.application.assisted.sources.fixture_files import FIXTURES_DIRECTORY

PAGE = (FIXTURES_DIRECTORY / "pasted_page.txt").read_text()


def fake_llm(reply: str):
    captured: dict[str, str] = {}

    async def call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        captured["prompt"] = prompt
        return reply

    return call, captured
