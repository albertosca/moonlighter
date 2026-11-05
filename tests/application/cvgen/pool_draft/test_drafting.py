import json

from moonlighter.application.cvgen.pool import CVPool
from moonlighter.application.cvgen.pool_draft import draft_pool

from tests.application.cvgen.bootstrap_samples import CANDIDATE_PROFILE, scripted_caller
from tests.application.cvgen.log_records import logged_warnings
from tests.application.cvgen.tailored_cv_samples import fixed_caller


async def test_draft_pool_turns_a_profile_into_a_cv_pool():
    pool = await draft_pool(CANDIDATE_PROFILE, scripted_caller())
    assert isinstance(pool, CVPool)
    assert pool.experiences[0].company == "Acme Corp"
    assert pool.experiences[0].location == "Remote (Brazil)"  # profile's top-level fallback
    bullet = pool.experiences[0].bullets[0]
    assert bullet.id == "acme-migration"
    assert bullet.angles == ("backend",)
    # escape_latex applied: **bold** markdown becomes \textbf{}, not raw asterisks
    assert r"\textbf{p99 latency by 40\%}" in bullet.latex


async def test_draft_pool_dedupes_a_repeated_bullet_id():
    dupe_response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Acme",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [
                        {"id": "acme-a", "angles": [], "text": "First"},
                        {"id": "acme-a", "angles": [], "text": "Second"},
                    ],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(CANDIDATE_PROFILE, scripted_caller(dupe_response))
    ids = [bullet.id for error in pool.experiences for bullet in error.bullets]
    assert ids == ["acme-a", "acme-a-2"]


async def test_draft_pool_drops_a_non_typesettable_bullet_with_a_warning(caplog):
    bad_response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Acme",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [
                        {"id": "acme-emoji", "angles": [], "text": "Shipped it 🚀"},
                        {"id": "acme-ok", "angles": [], "text": "Shipped it well"},
                    ],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(CANDIDATE_PROFILE, scripted_caller(bad_response))
    ids = [bullet.id for error in pool.experiences for bullet in error.bullets]
    assert ids == ["acme-ok"]


async def test_draft_pool_disambiguates_a_third_repeated_bullet_id():
    triple_response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Acme",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [
                        {"id": "acme-a", "angles": [], "text": "First"},
                        {"id": "acme-a", "angles": [], "text": "Second"},
                        {"id": "acme-a", "angles": [], "text": "Third"},
                    ],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(CANDIDATE_PROFILE, scripted_caller(triple_response))
    ids = [bullet.id for error in pool.experiences for bullet in error.bullets]
    assert ids == ["acme-a", "acme-a-2", "acme-a-3"]


async def test_draft_pool_skips_a_bullet_that_is_not_a_mapping():
    mixed_response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Acme",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [
                        "not a mapping",
                        {"id": "acme-ok", "angles": [], "text": "Shipped it well"},
                    ],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(CANDIDATE_PROFILE, scripted_caller(mixed_response))
    ids = [bullet.id for error in pool.experiences for bullet in error.bullets]
    assert ids == ["acme-ok"]


async def test_draft_pool_drops_a_bullet_that_escapes_to_nothing():
    # A zero-width space is not whitespace (str.strip() leaves it) and is
    # invisible to is_typesettable (Cf is dropped before the allow-list
    # check), so it survives both guards -- but escape_latex's own Cf-drop
    # + strip then collapses it to "", and an empty bullet must not render.
    zwsp_response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Acme",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [
                        {"id": "acme-empty", "angles": [], "text": "\u200b"},
                        {"id": "acme-ok", "angles": [], "text": "Shipped it well"},
                    ],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(CANDIDATE_PROFILE, scripted_caller(zwsp_response))
    ids = [bullet.id for error in pool.experiences for bullet in error.bullets]
    assert ids == ["acme-ok"]


async def test_draft_pool_escapes_a_tex_special_in_the_experience_header_fields():
    # pool.py's own module docstring records this exact bug already happening once:
    # an unescaped '&' in a hand-curated "R&D Engineer" title broke every pdflatex
    # compile silently until someone compiled it. render.py's _entry pastes company/
    # title/period/location into \cventry{...} unescaped, trusting they are already
    # curated LaTeX -- a model-echoed "AT&T" from the profile is not, so
    # _experience_from_raw must run these four fields through escape_latex exactly
    # like bullet text, not just pass them through raw.
    special_response = json.dumps(
        {
            "experiences": [
                {
                    "company": "AT&T",
                    "title": "R&D Engineer",
                    "period": "2020",
                    "bullets": [{"id": "att-ok", "angles": [], "text": "Shipped it well"}],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(CANDIDATE_PROFILE, scripted_caller(special_response))
    exp = pool.experiences[0]
    assert exp.company == r"AT\&T"
    assert exp.title == r"R\&D Engineer"


async def test_a_dropped_bootstrap_bullet_is_named_by_its_id(caplog):
    response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Acme",
                    "bullets": [
                        {"id": "ok", "angles": [], "text": "Fine"},
                        {"id": "bad", "angles": [], "text": "Ships \U0001f680"},
                    ],
                }
            ]
        }
    )
    pool = await draft_pool({"experience": [{"company": "Acme"}]}, fixed_caller(response))
    assert [bullet.id for bullet in pool.experiences[0].bullets] == ["ok"]
    assert logged_warnings(caplog) == [
        "bootstrap: dropping a non-typesettable or empty bullet (id='bad')"
    ]
