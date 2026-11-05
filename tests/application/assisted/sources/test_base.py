import httpx
from moonlighter.application.assisted.sources.base import (
    SourceMatch,
    questions_or_empty,
    required_fields_or_empty,
)


class _UnreachableSource:
    name = "unreachable"

    def match(self, job):
        return None

    async def questions(self, match, client):
        raise httpx.ConnectTimeout("the ATS took too long")

    async def required_fields(self, match, client):
        raise httpx.ConnectTimeout("the ATS took too long")


class _UnreadableSource:
    name = "unreadable"

    def match(self, job):
        return None

    async def questions(self, match, client):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    async def required_fields(self, match, client):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


async def test_a_source_that_cannot_be_reached_has_no_questions():
    match = SourceMatch(_UnreachableSource(), ())
    async with httpx.AsyncClient() as client:
        assert await questions_or_empty(match, client) == []
        assert await required_fields_or_empty(match, client) == ()


async def test_the_adapted_sources_publish_no_separate_required_fields():
    from moonlighter.application.assisted.sources.greenhouse import GreenhouseSource
    from moonlighter.application.assisted.sources.recruitee import RecruiteeSource

    async with httpx.AsyncClient() as client:
        for source in (GreenhouseSource(), RecruiteeSource()):
            assert await source.required_fields(SourceMatch(source, ("a", "b")), client) == ()


async def test_a_source_whose_body_cannot_be_read_has_no_questions():
    match = SourceMatch(_UnreadableSource(), ())
    async with httpx.AsyncClient() as client:
        assert await questions_or_empty(match, client) == []
        assert await required_fields_or_empty(match, client) == ()


class _MisshapenSource:
    name = "misshapen"

    def match(self, job):
        return None

    async def questions(self, match, client):
        raise TypeError("'int' object is not iterable")

    async def required_fields(self, match, client):
        raise AttributeError("'int' object has no attribute 'get'")


async def test_a_source_whose_payload_has_an_unexpected_shape_has_no_questions():
    # Workable `{"fields": 5}`, Greenhouse `questions: ["x"]`: a shape the parser
    # never anticipated must reach the person as the paste hint, not a crash.
    match = SourceMatch(_MisshapenSource(), ())
    async with httpx.AsyncClient() as client:
        assert await questions_or_empty(match, client) == []
        assert await required_fields_or_empty(match, client) == ()
