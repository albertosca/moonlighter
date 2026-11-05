"""The profile, job and fake LLM callers the composer's tests share."""

PROFILE = {"name": "Alberto de Sá Cavalcanti de Albuquerque", "email": "a@example.com"}
JOB = {"title": "Staff Engineer", "company": "acme", "description": "..."}


async def never_called(prompt: str, model: str, cache_prefix: str | None = None) -> str:
    raise AssertionError("the LLM must not be consulted for a field the profile answers")


async def answers_anything(prompt: str, model: str, cache_prefix: str | None = None) -> str:
    return "a generated answer"
