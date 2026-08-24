from moonlighter.application.answers.profile import profile_for_answers


def test_profile_for_answers_keeps_only_prose_keys():
    full = {
        "name": "Alberto X",
        "phone": "5581999",
        "email": "a@b.com",
        "linkedin": "in/x",
        "website": "x.com",
        "headline": "Staff Eng",
        "summary": "...",
        "skills": ["rust"],
        "experience": [{"a": 1}],
        "education": [{"b": 2}],
        "languages": ["pt"],
        "publications": ["p"],
        "open_source": [{"name": "moonlighter"}],
        "preferences": {"salary_target_brl_monthly": 40000},
        "criteria": {"priority_targets": ["Nubank"]},
    }
    reduced = profile_for_answers(full)
    assert set(reduced) == {
        "headline",
        "summary",
        "skills",
        "experience",
        "education",
        "languages",
        "publications",
        "open_source",
    }
    # The secrets are gone.
    assert "phone" not in reduced and "email" not in reduced
    assert "preferences" not in reduced and "criteria" not in reduced


def test_profile_for_answers_omits_absent_keys():
    reduced = profile_for_answers({"summary": "s"})
    assert reduced == {"summary": "s"}


def test_career_start_reaches_the_answer_prompt():
    """The experience list starts at the first formal contract, so the model
    counted from there and wrote "close to 14 years" for someone with 16 — an
    understatement repeated in every application, including a screening question
    that asks about years of experience. The whitelist is what decides whether a
    profile field can influence an answer at all."""
    profile = {
        "career_started": 2010,
        "experience": [{"company": "X", "period": "2012-09 – 2014-07"}],
        "summary": "s",
    }
    assert profile_for_answers(profile)["career_started"] == 2010


def test_profile_for_answers_still_excludes_contact_details():
    """The whitelist exists because this output lands on an untrusted page:
    contact data is placed by the deterministic field map, never written by the
    model into free text."""
    profile = {"name": "X", "email": "a@b.c", "phone": "1", "linkedin": "u", "summary": "s"}
    sent = profile_for_answers(profile)
    assert set(sent) == {"summary"}


def test_open_source_reaches_the_answer_prompt():
    """Seen live twice on 2026-08-21 (Supabase DevRel #8138 and Frontend #5100):
    "open source contributions" answers cited only ParallelME (2016) from the
    experience list and ignored the projects in profile.yaml's open_source: —
    the whitelist never let them through. Public by nature; prose content, not
    contact data (links stay on the deterministic field-map track)."""
    profile = {"open_source": [{"name": "moonlighter"}], "summary": "s"}
    assert profile_for_answers(profile)["open_source"] == [{"name": "moonlighter"}]
