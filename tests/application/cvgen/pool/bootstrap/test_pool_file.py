import json

import pytest

from moonlighter.application.cvgen.pool.bootstrap import BootstrapOutcome, bootstrap_cv_pool
from moonlighter.application.cvgen.pool.bootstrap_error import BootstrapError
from moonlighter.application.cvgen.pool.loader import load_pool
from tests.application.cvgen.sample_bootstrap import CANDIDATE_PROFILE, scripted_caller


async def test_bootstrap_cv_pool_place_holds_a_missing_title_and_period(monkeypatch, tmp_path):
    # pool/loader.py's _experience rejects an EMPTY title/period with PoolError just
    # as hard as an empty location, and a model that omits either is ordinary
    # -- location already had a placeholder guard, these two fell through to
    # "". The proof is the round trip, not the field: a pool that load_pool
    # refuses to read is a pool ensure_tailored_cv silently ignores forever.
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    thin_response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Acme",
                    "bullets": [{"id": "acme-ok", "angles": [], "text": "Shipped it well"}],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    outcome = await bootstrap_cv_pool(CANDIDATE_PROFILE, {}, scripted_caller(thin_response))

    reloaded = load_pool(outcome.pool_path)
    exp = reloaded.experiences[0]
    assert exp.title == "Title not specified"
    assert exp.period == "Period not specified"
    assert exp.location == "Remote (Brazil)"  # CANDIDATE_PROFILE's own top-level location


async def test_bootstrap_cv_pool_refuses_to_report_success_on_an_unloadable_pool(
    monkeypatch, tmp_path
):
    # Validate-what-you-wrote closes the CLASS the two guards above only
    # patch two instances of. A zero-width space is a truthy company (so the
    # entry is kept) that escape_latex then reduces to "" (Cf is dropped) --
    # dump_pool happily serializes it and load_pool refuses it. Without this
    # check the bootstrap reports N bullets drafted and every later
    # prepare_application quietly skips the file.
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    zwsp_company = json.dumps(
        {
            "experiences": [
                {
                    "company": "\u200b",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "acme-ok", "angles": [], "text": "Shipped it well"}],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    with pytest.raises(BootstrapError, match="not loadable"):
        await bootstrap_cv_pool(CANDIDATE_PROFILE, {}, scripted_caller(zwsp_company))

    # write-to-temp-then-rename: a failed validation must leave NOTHING at
    # the real pool_path -- not a half-written pool for _cv_bootstrap_offer
    # to see and stop offering forever, and not a garbage file for
    # ensure_tailored_cv to silently degrade past. The temp file itself must
    # also be gone, not just orphaned next to the real path.
    assert not (tmp_path / "cv-pool.yaml").exists()
    assert not (tmp_path / "cv-pool.yaml.tmp").exists()


async def test_bootstrap_cv_pool_force_preserves_the_previous_pool_on_a_failed_draft(
    monkeypatch, tmp_path
):
    # Under force=True, the real pool_path holds the operator's previous,
    # perfectly good pool at the moment bootstrap_cv_pool is called. If the
    # NEW draft fails load_pool validation, that previous pool must survive
    # untouched -- the write-to-temp-then-rename approach makes this true by
    # construction, since the real path is never written to until the temp
    # file has already proven loadable.
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    previous_pool = (
        "experiences:\n"
        "  - company: Previous Co\n"
        "    title: Engineer\n"
        "    period: 2018 - 2020\n"
        "    location: Remote\n"
        "    bullets:\n"
        "      - id: previous-bullet\n"
        "        angles: []\n"
        "        latex: Did the previous thing.\n"
    )
    (tmp_path / "cv-pool.yaml").write_text(previous_pool)

    zwsp_company = json.dumps(
        {
            "experiences": [
                {
                    "company": "\u200b",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "acme-ok", "angles": [], "text": "Shipped it well"}],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    with pytest.raises(BootstrapError, match="not loadable"):
        await bootstrap_cv_pool(CANDIDATE_PROFILE, {}, scripted_caller(zwsp_company), force=True)

    reloaded = load_pool(tmp_path / "cv-pool.yaml")
    assert reloaded.experiences[0].company == "Previous Co"
    assert not (tmp_path / "cv-pool.yaml.tmp").exists()


async def test_bootstrap_cv_pool_writes_pool_template_and_compiled_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    profile = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "experience": [
            {
                "company": "Acme",
                "role": "Engineer",
                "period": "2020",
                "highlights": ["Did the thing."],
            }
        ],
    }
    outcome = await bootstrap_cv_pool(profile, {}, scripted_caller())
    assert isinstance(outcome, BootstrapOutcome)
    assert outcome.pool_path == tmp_path / "cv-pool.yaml"
    assert outcome.pool_path.exists()
    assert outcome.pool_path.read_text().startswith("# DRAFT")
    assert outcome.template_path == tmp_path / "cv-templates" / "cv-template.en.tex"
    assert outcome.template_path.exists()
    assert outcome.bullet_count == 1


async def test_bootstrap_cv_pool_refuses_to_overwrite_an_existing_pool(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "cv-pool.yaml").write_text("experiences: []\n")
    profile = {
        "name": "Jane Doe",
        "experience": [{"company": "Acme", "role": "Eng", "period": "2020", "highlights": ["X"]}],
    }
    with pytest.raises(BootstrapError, match="already exists"):
        await bootstrap_cv_pool(profile, {}, scripted_caller())


async def test_bootstrap_cv_pool_force_overwrites_an_existing_pool(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "cv-pool.yaml").write_text("experiences: []\n")
    profile = {
        "name": "Jane Doe",
        "experience": [{"company": "Acme", "role": "Eng", "period": "2020", "highlights": ["X"]}],
    }
    outcome = await bootstrap_cv_pool(profile, {}, scripted_caller(), force=True)
    assert outcome.bullet_count == 1
