import importlib.resources
import json

import pytest
from moonlighter.application.cvgen.bootstrap import bootstrap_cv_pool
from moonlighter.application.cvgen.compile import latex_available, looks_like_a_compiled_pdf
from moonlighter.application.cvgen.paths import resolved_pool_path
from moonlighter.application.cvgen.pool import load_pool
from moonlighter.application.cvgen.service import ensure_tailored_cv

from tests.application.cvgen.bootstrap_samples import scripted_caller

REAL_PROFILE = {
    "name": "Jane Marie Doe",
    "headline": "Senior Software Engineer",
    "email": "jane@example.com",
    "phone": "+1 555 0100",
    "linkedin": "https://www.linkedin.com/in/janedoe/",
    "location": "Remote (Brazil)",
    "education": [{"degree": "BSc Computer Science", "school": "Example University", "year": 2014}],
    "experience": [
        {
            "company": "Acme Corp",
            "role": "Senior Software Engineer",
            "period": "2020 - present",
            "highlights": ["Led the migration of a monolith to services."],
        }
    ],
}


DECIDE_RESPONSE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "Senior engineer with **10+ years** building backend systems.",
        "technical_expertise": "Backend, APIs, distributed systems",
        "bullets": ["acme-migration"],
        "open_source": [],
    }
)


def test_the_example_template_and_pool_ship_as_package_data():
    # Proves the files are reachable the way fill_template()/draft_pool()
    # will read them -- importlib.resources, not a hardcoded filesystem path that
    # only works from a repo checkout. This is the packaging gap the spec's
    # mid-planning correction exists to close.
    templates = importlib.resources.files("moonlighter.application.cvgen.templates")
    pool_text = (templates / "cv-pool.example.yaml").read_text()
    template_text = (templates / "cv-template.en.example.tex").read_text()
    assert "experiences:" in pool_text
    assert "{{NAME_FIRST}}" in template_text
    assert "%%SUMMARY%%" in template_text


async def test_bootstrap_cv_pool_output_is_immediately_usable_by_ensure_tailored_cv(
    monkeypatch, tmp_path
):
    # The guardrail decision (spec: comment header only, no code-level lock):
    # proves nothing added in this plan blocks the very next ensure_tailored_cv
    # call from reading the pool this same bootstrap just wrote -- the DRAFT
    # comment is a YAML comment, invisible to load_pool, not a lock file.
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    profile = {
        "name": "Jane Doe",
        "experience": [
            {"company": "Acme", "role": "Eng", "period": "2020", "highlights": ["Did X."]}
        ],
    }
    await bootstrap_cv_pool(profile, {}, scripted_caller())

    pool = load_pool(resolved_pool_path({}))
    # scripted_caller()'s default response is the module-level DRAFT_RESPONSE fixture
    # (a canned LLM reply, like every other draft_pool test above) -- it does
    # not parse `profile`, so the drafted company is DRAFT_RESPONSE's own
    # "Acme Corp", not this test's local profile["experience"][0]["company"].
    # What this test actually proves -- the only thing its own comment above
    # claims -- is that load_pool can read back what bootstrap_cv_pool wrote.
    assert pool.experiences[0].company == "Acme Corp"


@pytest.mark.skipif(not latex_available(), reason="pdflatex not installed")
async def test_bootstrap_output_compiles_and_feeds_the_per_job_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    outcome = await bootstrap_cv_pool(REAL_PROFILE, {}, scripted_caller())

    # Not `is None or exists()`: a real PDF, or this fails.
    assert outcome.pdf_path is not None
    assert outcome.pdf_path.exists()
    assert looks_like_a_compiled_pdf(outcome.pdf_path)

    # And the pool + template it just wrote are a working INPUT to the per-job
    # engine -- the whole point of bootstrapping them.
    job = {
        "id": 1,
        "company": "Globex",
        "title": "Backend Engineer",
        "description": "We need a backend engineer for our distributed services.",
    }
    tailored = await ensure_tailored_cv(
        job, {}, REAL_PROFILE, caller=scripted_caller(DECIDE_RESPONSE)
    )
    assert tailored is not None
    assert tailored.compiled is True
    assert looks_like_a_compiled_pdf(tailored.path)
