import httpx
import pytest
from moonlighter.application.assisted.composed_answer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.core.db import Job, init_db


@pytest.fixture
def job_factory(temporary_database):
    """Create a Job row in the in-memory test database.

    The shared temporary_database fixture points MOONLIGHTER_DB_PATH at a fresh temp
    file, init_db() creates the schema in it, and Job.create() persists the row callers
    ask for.
    """
    init_db()

    def _make(**overrides: object) -> Job:
        defaults: dict[str, object] = {
            "source": "greenhouse",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://boards.greenhouse.io/acme/jobs/1",
            "status": "new",
        }
        defaults.update(overrides)
        return Job.create(**defaults)

    return _make


@pytest.fixture(autouse=True)
def _no_real_network(request, monkeypatch):
    """A unit test that reaches a real ATS is a bug: fail it loudly.

    MockTransport is unaffected (it never reaches AsyncHTTPTransport); e2e
    tests opt out because talking to the real ATS is their point.
    """
    if request.node.get_closest_marker("e2e") is not None:
        return

    async def refuse(self, http_request):
        raise AssertionError(f"real network call in a unit test: {http_request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


@pytest.fixture
def composed_fixture():
    """Two answered, required text questions: the sheet the result tests render."""
    return [
        ComposedAnswer(
            FormQuestion(label="Full name", kind=QuestionKind.TEXT, options=[], required=True),
            "Jane Doe",
            None,
        ),
        ComposedAnswer(
            FormQuestion(label="Email", kind=QuestionKind.TEXT, options=[], required=True),
            "jane@example.com",
            None,
        ),
    ]
