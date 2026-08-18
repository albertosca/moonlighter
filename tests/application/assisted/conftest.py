import pytest
from moonlighter.core.db import Job, init_db


@pytest.fixture
def job_factory(tmp_db):
    """Create a Job row in the in-memory test database.

    Follows the pattern used in tests/application/test_service.py: tmp_db
    points MOONLIGHTER_DB_PATH at a fresh temp file, init_db() creates the
    schema in it, and Job.create() persists the row callers ask for.
    """
    init_db()

    def _make(**kwargs: object) -> Job:
        defaults: dict[str, object] = {
            "source": "greenhouse",
            "company": "Acme",
            "title": "Engineer",
            "url": "https://boards.greenhouse.io/acme/jobs/1",
            "status": "new",
        }
        defaults.update(kwargs)
        return Job.create(**defaults)

    return _make
