"""The job, config, profile and questions the sheet-result tests prepare applications from."""

from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.core.db import Job, init_db, record_cv_bootstrap_decline

CONFIG = {"llm_model": "claude-sonnet-4-6"}
PROFILE = {"name": "Jane Doe", "email": "jane@example.com"}
QUESTIONS = [
    FormQuestion(label="Full name", kind=QuestionKind.TEXT, options=[], required=True),
    FormQuestion(label="Email", kind=QuestionKind.TEXT, options=[], required=True),
]
PAGE = "Full name\nEmail\nWhy do you want to work here?"


def create_job(**overrides):
    init_db()
    # Recording a decline keeps the CV-pool bootstrap offer a no-op, so these tests
    # assert on sheet, paste-hint and error content without touching resolved_pool_path
    # (the offer itself is tested in service/).
    record_cv_bootstrap_decline()
    defaults = {
        "source": "greenhouse",
        "company": "Acme",
        "title": "Staff Engineer",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "score": 9.0,
        "status": "new",
    }
    defaults.update(overrides)
    return Job.create(**defaults)
