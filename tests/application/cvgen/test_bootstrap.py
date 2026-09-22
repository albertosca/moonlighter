"""Tests for the CV-pool bootstrap (draft_pool, fill_template, bootstrap_cv_pool)."""

import importlib.resources
import json

import pytest
from moonlighter.application.cvgen.bootstrap import (
    BootstrapError,
    BootstrapOutcome,
    bootstrap_cv_pool,
    draft_pool,
    fill_template,
)
from moonlighter.application.cvgen.compile import latex_available, looks_like_a_compiled_pdf
from moonlighter.application.cvgen.pool import CVPool
from moonlighter.application.cvgen.service import ensure_tailored_cv


def test_the_example_template_and_pool_ship_as_package_data():
    # Proves the files are reachable the way fill_template()/draft_pool() (Task 6)
    # will read them -- importlib.resources, not a hardcoded filesystem path that
    # only works from a repo checkout. This is the packaging gap the spec's
    # mid-planning correction exists to close.
    templates = importlib.resources.files("moonlighter.application.cvgen.templates")
    pool_text = (templates / "cv-pool.example.yaml").read_text()
    template_text = (templates / "cv-template.en.example.tex").read_text()
    assert "experiences:" in pool_text
    assert "{{NAME_FIRST}}" in template_text
    assert "%%SUMMARY%%" in template_text


PROFILE = {
    "name": "Jane Doe",
    "location": "Remote (Brazil)",
    "summary": "Senior engineer.",
    "skills": ["Python", "Go"],
    "experience": [
        {
            "company": "Acme Corp",
            "role": "Senior Software Engineer",
            "period": "2020 - present",
            "highlights": ["Led the migration of a monolith to services, cutting p99 by 40%."],
        }
    ],
}

DRAFT_RESPONSE = json.dumps(
    {
        "experiences": [
            {
                "company": "Acme Corp",
                "title": "Senior Software Engineer",
                "period": "2020 - present",
                "bullets": [
                    {
                        "id": "acme-migration",
                        "angles": ["backend"],
                        "text": "Led the migration of a monolith to services, cutting **p99 latency by 40%**.",
                    }
                ],
            }
        ],
        "open_source": [],
        "summary_facts": ["10+ years of experience"],
    }
)


def _caller(response: str = DRAFT_RESPONSE):
    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return response

    return _call


async def test_draft_pool_turns_a_profile_into_a_cv_pool():
    pool = await draft_pool(PROFILE, _caller())
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
    pool = await draft_pool(PROFILE, _caller(dupe_response))
    ids = [b.id for e in pool.experiences for b in e.bullets]
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
    pool = await draft_pool(PROFILE, _caller(bad_response))
    ids = [b.id for e in pool.experiences for b in e.bullets]
    assert ids == ["acme-ok"]


async def test_draft_pool_raises_when_the_profile_has_no_experience():
    with pytest.raises(BootstrapError, match="no experience"):
        await draft_pool({"name": "Jane"}, _caller())


async def test_draft_pool_raises_when_the_model_response_is_unusable():
    with pytest.raises(BootstrapError, match="could not be parsed"):
        await draft_pool(PROFILE, _caller("not json"))


async def test_draft_pool_reraises_a_spend_limit():
    async def _quota_exceeded(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise RuntimeError("spend limit reached")

    with pytest.raises(RuntimeError, match="spend limit"):
        await draft_pool(PROFILE, _quota_exceeded)


# The 7 cases above are the plan's brief verbatim. The repo's coverage gate
# (--cov-fail-under=100, whole-tree) is a hard requirement (see CLAUDE.md),
# and the branches below -- a 3rd repeat id, a malformed bullet, a bullet
# that escapes to nothing, a company-less experience, an experience whose
# only bullet gets dropped, a non-spend-limit call failure, and a
# shape-valid-but-empty response -- are real deterministic-validation paths
# a security-sensitive drafting function must not leave silently untested.


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
    pool = await draft_pool(PROFILE, _caller(triple_response))
    ids = [b.id for e in pool.experiences for b in e.bullets]
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
    pool = await draft_pool(PROFILE, _caller(mixed_response))
    ids = [b.id for e in pool.experiences for b in e.bullets]
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
    pool = await draft_pool(PROFILE, _caller(zwsp_response))
    ids = [b.id for e in pool.experiences for b in e.bullets]
    assert ids == ["acme-ok"]


async def test_draft_pool_skips_an_experience_entry_missing_a_company():
    no_company_response = json.dumps(
        {
            "experiences": [
                {
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "x", "angles": [], "text": "No company here"}],
                },
                {
                    "company": "Acme",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "acme-ok", "angles": [], "text": "Shipped it well"}],
                },
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(PROFILE, _caller(no_company_response))
    assert [e.company for e in pool.experiences] == ["Acme"]


async def test_draft_pool_drops_an_experience_when_every_bullet_is_dropped():
    dropped_response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Bad Co",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "bad", "angles": [], "text": "Shipped it 🚀"}],
                },
                {
                    "company": "Acme",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "acme-ok", "angles": [], "text": "Shipped it well"}],
                },
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(PROFILE, _caller(dropped_response))
    assert [e.company for e in pool.experiences] == ["Acme"]


async def test_draft_pool_raises_when_the_call_fails_for_a_non_spend_limit_reason():
    async def _broken(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise RuntimeError("connection reset")

    with pytest.raises(BootstrapError, match="drafting call failed"):
        await draft_pool(PROFILE, _broken)


async def test_draft_pool_raises_when_the_response_has_no_experiences_key():
    with pytest.raises(BootstrapError, match="could not be parsed into a CV pool"):
        await draft_pool(PROFILE, _caller(json.dumps({"foo": "bar"})))


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
    pool = await draft_pool(PROFILE, _caller(special_response))
    exp = pool.experiences[0]
    assert exp.company == r"AT\&T"
    assert exp.title == r"R\&D Engineer"


async def test_draft_pool_raises_when_every_experience_is_unusable():
    unusable_response = json.dumps(
        {
            "experiences": [
                {
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "x", "angles": [], "text": "No company"}],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    with pytest.raises(BootstrapError, match="no usable experience"):
        await draft_pool(PROFILE, _caller(unusable_response))


async def test_bootstrap_cv_pool_place_holds_a_missing_title_and_period(monkeypatch, tmp_path):
    # pool.py's _experience rejects an EMPTY title/period with PoolError just
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
    outcome = await bootstrap_cv_pool(PROFILE, {}, _caller(thin_response))

    from moonlighter.application.cvgen.pool import load_pool

    reloaded = load_pool(outcome.pool_path)
    exp = reloaded.experiences[0]
    assert exp.title == "Title not specified"
    assert exp.period == "Period not specified"
    assert exp.location == "Remote (Brazil)"  # PROFILE's own top-level location


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
                    "company": "​",
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
        await bootstrap_cv_pool(PROFILE, {}, _caller(zwsp_company))

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
                    "company": "​",
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
        await bootstrap_cv_pool(PROFILE, {}, _caller(zwsp_company), force=True)

    from moonlighter.application.cvgen.pool import load_pool

    reloaded = load_pool(tmp_path / "cv-pool.yaml")
    assert reloaded.experiences[0].company == "Previous Co"
    assert not (tmp_path / "cv-pool.yaml.tmp").exists()


def test_fill_template_substitutes_contact_and_education_placeholders():
    profile = {
        "name": "Jane Marie Doe",
        "headline": "Senior Engineer",
        "email": "jane@example.com",
        "phone": "+1 555 0100",
        "linkedin": "https://www.linkedin.com/in/janedoe/",
        "education": [
            {"degree": "BSc Computer Science", "school": "Example University", "year": 2014}
        ],
    }
    filled = fill_template(profile)
    assert "{{" not in filled  # every {{...}} placeholder was substituted
    assert "%%SUMMARY%%" in filled  # the per-job markers survive untouched
    assert r"\firstname{Jane Marie}" in filled
    assert r"\familyname{Doe}" in filled
    assert r"\email{jane@example.com}" in filled
    assert r"\social[linkedin]{janedoe}" in filled
    assert "BSc Computer Science" in filled
    assert "Example University" in filled


def test_fill_template_handles_a_missing_optional_field():
    filled = fill_template({"name": "Jane Doe"})
    assert "{{" not in filled
    assert r"\phone[mobile]{}" in filled


def test_fill_template_escapes_tex_specials_in_contact_and_education_fields():
    # pool.py's own module docstring records this exact bug class already
    # happening once: an unescaped '&' in a hand-curated "R&D Engineer" title
    # broke every pdflatex compile silently. NAME_FIRST/NAME_LAST/HEADLINE/
    # PHONE/EMAIL and the education fields all substitute into ordinary
    # text-mode LaTeX macros (\firstname{}, \title{}, \phone[mobile]{},
    # \email{}, \cventry{...}) -- not verbatim -- so a profile.yaml field
    # containing a TeX special must come out escaped, not raw. A bare '%' is
    # the sharpest case: unescaped, it is LaTeX's comment character and
    # silently truncates the rest of the line with no compile error at all.
    profile = {
        "name": "Anne & Marie Doe",
        "headline": "Full-Stack Engineer (Node.js & React, 100% remote)",
        "phone": "+1 555 0100 #2",
        "email": "jane_doe@example.com",
        "education": [
            {"degree": "R&D Engineering", "school": "50% Scholarship University", "year": 2014}
        ],
    }
    filled = fill_template(profile)
    assert r"\firstname{Anne \& Marie}" in filled
    assert r"\familyname{Doe}" in filled
    assert r"\title{Full-Stack Engineer (Node.js \& React, 100\% remote)}" in filled
    assert r"\phone[mobile]{+1 555 0100 \#2}" in filled
    assert r"\email{jane\_doe@example.com}" in filled
    assert r"R\&D Engineering" in filled
    assert r"50\% Scholarship University" in filled
    # LINKEDIN_USERNAME is the one deliberate exception: it is a slug already
    # parsed out of a URL, never free text, so it is never escaped.


def test_fill_template_drops_a_linkedin_value_that_is_not_a_real_slug():
    # LINKEDIN_USERNAME is the one substitution fill_template leaves
    # UNESCAPED, justified by "it's a slug, never free text" -- so the
    # pattern has to enforce that, and "anything but /?#" did not. A '%' is
    # LaTeX's comment character: unescaped inside \social[linkedin]{...} it
    # eats the closing brace and the rest of the line, with no compile error
    # at the point of the mistake. A value that is not a slug now yields
    # nothing at all rather than something unsafe.
    filled = fill_template(
        {"name": "Jane Doe", "linkedin": "https://www.linkedin.com/in/jane%doe}\\evil"}
    )
    assert r"\social[linkedin]{}" in filled
    assert "%doe" not in filled
    assert "evil" not in filled
    # And a legitimate slug is still lossless, hyphen and digits included.
    ok = fill_template({"name": "Jane Doe", "linkedin": "https://linkedin.com/in/jane-doe-42"})
    assert r"\social[linkedin]{jane-doe-42}" in ok


def test_fill_template_skips_a_malformed_education_entry_that_is_not_a_mapping():
    # profile.yaml is hand-edited: a stray '-' under "education" (the same
    # mistake pool.py's own _bullet/_experience guard against) makes an entry
    # a bare string instead of a mapping -- fill_template must skip it rather
    # than crash the whole bootstrap on one malformed line.
    profile = {
        "name": "Jane Doe",
        "education": [
            "not a mapping",
            {"degree": "BSc Computer Science", "school": "Example University", "year": 2014},
        ],
    }
    filled = fill_template(profile)
    assert "{{" not in filled
    assert "BSc Computer Science" in filled
    assert "not a mapping" not in filled


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
    outcome = await bootstrap_cv_pool(profile, {}, _caller())
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
        await bootstrap_cv_pool(profile, {}, _caller())


async def test_bootstrap_cv_pool_force_overwrites_an_existing_pool(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "cv-pool.yaml").write_text("experiences: []\n")
    profile = {
        "name": "Jane Doe",
        "experience": [{"company": "Acme", "role": "Eng", "period": "2020", "highlights": ["X"]}],
    }
    outcome = await bootstrap_cv_pool(profile, {}, _caller(), force=True)
    assert outcome.bullet_count == 1


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
    await bootstrap_cv_pool(profile, {}, _caller())

    from moonlighter.application.cvgen.pool import load_pool
    from moonlighter.application.cvgen.service import resolved_pool_path

    pool = load_pool(resolved_pool_path({}))
    # _caller()'s default response is the module-level DRAFT_RESPONSE fixture
    # (a canned LLM reply, like every other draft_pool test above) -- it does
    # not parse `profile`, so the drafted company is DRAFT_RESPONSE's own
    # "Acme Corp", not this test's local profile["experience"][0]["company"].
    # What this test actually proves -- the only thing its own comment above
    # claims -- is that load_pool can read back what bootstrap_cv_pool wrote.
    assert pool.experiences[0].company == "Acme Corp"


# --- The end-to-end compile proof -------------------------------------------
#
# Every assertion above stops at "a file was written." None of them ever asked
# pdflatex whether that file is a DOCUMENT, and the two bugs this test exists
# to catch both lived in exactly that gap for ten rounds of review:
#   1. bootstrap_cv_pool compiled the raw template, markers and all, so
#      \cvlistitem{ + a per-job marker opened a group whose closing brace the
#      LaTeX comment character then swallowed -- pdf_path was None on EVERY
#      machine, and the MCP tool blamed a missing pdflatex for it.
#   2. the shipped example template's own header comment SPELLED the per-job
#      markers, and render_cv's blind str.replace substituted them there too;
#      the experience block is multi-line, so its tail landed as live LaTeX
#      before \documentclass and failed every per-job render as well.
# The old assertion here was `pdf_path is None or pdf_path.exists()` -- true
# whether compilation succeeded or failed, which is why neither bug showed.
# This one demands a real PDF from a real pdflatex, and then walks the
# bootstrap's output through the per-job pipeline it exists to feed.

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


@pytest.mark.skipif(not latex_available(), reason="pdflatex not installed")
async def test_bootstrap_output_compiles_and_feeds_the_per_job_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    outcome = await bootstrap_cv_pool(REAL_PROFILE, {}, _caller())

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
    tailored = await ensure_tailored_cv(job, {}, REAL_PROFILE, _caller(DECIDE_RESPONSE))
    assert tailored is not None
    assert tailored.compiled is True
    assert looks_like_a_compiled_pdf(tailored.path)
