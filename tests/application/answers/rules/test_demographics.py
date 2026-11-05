"""EEO answers: only an exact self-identification label is served the configured value."""

import pytest

from moonlighter.application.answers.matching.field_map import pre_populate_answers
from moonlighter.application.answers.rules.demographics import demographic_answer
from tests.application.answers.candidate_profiles import PROFILE

# EEO/demographics: demographic_answer, NOT the _RULES ladder
# These live outside pre_populate_answers on purpose: composer's is_sensitive_label
# guard intercepts a demographic label before `known` is consulted, so a rule in
# _RULES would be unreachable — and putting the carve-out in the general ladder is
# what broke on 2026-09-11 (see the composer tests for the measured cases).


def test_a_demographic_label_is_not_answered_by_the_general_ladder():
    """The rules are deliberately NOT in _RULES: composer calls demographic_answer
    directly from inside its guard. If they were here, every other rule would get
    the same bypass.
    """
    for label in ["Gender", "Race", "Veteran status", "Disability status"]:
        assert label not in pre_populate_answers([label], PROFILE), label


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Gender", "Male"),
        ("Gender identity", "Male"),
        # Race and "Hispanic or Latino" are DISTINCT US EEO questions (a form may
        # ask both): race is White/Black/Asian/…, hispanic_latino is a separate
        # yes/no ethnicity question, from a different demographics key.
        ("Are you Hispanic or Latino?", "Yes"),
        ("Hispanic/Latino", "Yes"),
        ("Race", "White"),
        ("Race/Ethnicity", "White"),
        ("Veteran status", "No"),
        ("Protected veteran status", "No"),
        ("Disability status", "No"),
        ("Do you have a disability?", "No"),
    ],
)
def test_demographic_answer_reads_the_configured_value(label, expected):
    assert demographic_answer(label, PROFILE) == expected


@pytest.mark.parametrize(
    "label",
    [
        # CANARY: the first version of these patterns was unanchored, and `\brace\b`
        # answered this engineering essay with the word "White" on a real sheet.
        "Describe how you would debug a race condition in a concurrent system",
        "How would you improve our gender-neutral onboarding copy?",
        "Tell us about your work on accessibility for users with disabilities",
        "Are you currently based in Latino America?",
        "Professional references (name, email, LinkedIn)",
    ],
)
def test_demographic_answer_ignores_a_label_that_merely_mentions_the_word(label):
    assert demographic_answer(label, PROFILE) is None


@pytest.mark.parametrize(
    "label",
    [
        # SECOND CANARY, same defect one shape further in: start-anchoring alone let
        # any label that merely BEGINS with the category word through. Measured
        # 2026-09-13 — every one of these was answered with a real EEO value.
        # Same lesson the salary rule in salary.py already learned across three
        # failed widenings: anchor both ends, don't just anchor the start.
        "Veteran of the startup wars?",
        "Gender-neutral design experience?",
        "Race track preference?",
        "Race conditions: how do you debug them?",
        "Gender pay gap: your view?",
        "Disability insurance provider?",
        "Hispanic heritage month committee?",
    ],
)
def test_demographic_answer_ignores_a_label_that_merely_starts_with_the_word(label):
    assert demographic_answer(label, PROFILE) is None


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        # "Are you Hispanic/Latino?" is not hypothetical: it is a literal key in
        # Application.form_data in the live DB, alongside Gender / Veteran Status /
        # Disability Status — the Greenhouse EEO quartet. A first pass at anchoring
        # covered "are you hispanic or latino" and "hispanic/latino" but not the
        # cross product, so the commonest real spelling of the question this feature
        # exists to answer was the one it refused.
        ("Are you Hispanic/Latino?", "Yes"),
        ("Are you Hispanic or Latino?", "Yes"),
        # "(select all that apply)" is 21 characters, and the parenthetical strip was
        # bounded at 20 — off by one, on a real multi-select race question.
        ("Race (Select all that apply)", "White"),
        ("Race/ethnicity (select all that apply)", "White"),
        ("Gender (optional)", "Male"),
        ("Disability status (CC-305)", "No"),
    ],
)
def test_demographic_answer_handles_real_form_decoration(label, expected):
    assert demographic_answer(label, PROFILE) == expected


@pytest.mark.parametrize(
    "label",
    [
        # The blanket "strip any short parenthetical" rule cut both ways: it also
        # turned these into exact EEO matches. An allowlist of benign notes closes
        # the false negatives above and this window in the same change.
        "Disability (insurance)",
        "Veteran (of which war?)",
        "Gender (of your manager)",
        "Race (of the horse)",
    ],
)
def test_demographic_answer_does_not_strip_a_meaningful_parenthetical(label):
    assert demographic_answer(label, PROFILE) is None


def test_a_bare_ethnicity_label_is_not_served_the_race_value():
    """`Race/Ethnicity` is unambiguous — one combined question, answered from
    `race`. Bare `Ethnicity` is not: on a US EEO form it usually means the
    Hispanic/Latino question, so serving `race` there is a guess. This rule was
    unreachable until `Ethnicity` became a sensitive label (2026-09-14); rather
    than let the widening switch on a guess, the bare form stays a gap.
    """
    assert demographic_answer("Race/Ethnicity", PROFILE) == "White"
    assert demographic_answer("Ethnicity", PROFILE) is None


def test_demographic_answer_is_none_for_an_unset_key():
    profile = {**PROFILE, "demographics": {"gender": "Male"}}
    assert demographic_answer("Disability status", profile) is None
    assert demographic_answer("Gender", profile) == "Male"


def test_demographic_answer_is_none_without_a_demographics_block():
    assert demographic_answer("Gender", {"name": "X"}) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(True, "Yes"), (False, "No")],
)
def test_demographic_answer_coerces_a_yaml_boolean(raw, expected):
    """`profile.yaml` is read with yaml.safe_load (YAML 1.1), where an unquoted
    No/Yes parses as a bool. Left raw, False read as unconfigured (silently losing
    a configured answer) and True reached `known` as a non-str, crashing the whole
    sheet with AttributeError: 'bool' object has no attribute 'strip'.
    """
    profile = {**PROFILE, "demographics": {"veteran_status": raw}}
    assert demographic_answer("Veteran status", profile) == expected


def test_demographic_answer_treats_a_blank_string_as_unset():
    profile = {**PROFILE, "demographics": {"gender": "   "}}
    assert demographic_answer("Gender", profile) is None
