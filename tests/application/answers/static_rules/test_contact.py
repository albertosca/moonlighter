"""Contact rules: names, phone, email and profile links, from English labels."""

from moonlighter.application.answers.field_map import pre_populate_answers

from tests.application.answers.candidate_profiles import PROFILE


def test_first_name():
    result = pre_populate_answers(["First Name"], PROFILE)
    assert result["First Name"] == "Maria"


def test_last_name():
    result = pre_populate_answers(["Last Name"], PROFILE)
    assert result["Last Name"] == "de Souza Pereira"


def test_preferred_name():
    result = pre_populate_answers(["Preferred First Name"], PROFILE)
    assert result["Preferred First Name"] == "Maria"


def test_full_name():
    """A single "Full name" field is the norm outside the Greenhouse/Lever
    first+last convention. Without a rule it fell through to the LLM, which
    answered "full legal name is not present in the profile" -- leaving a
    required field blank on a real application (live Recruitee, 2026-08-03)."""
    result = pre_populate_answers(["Full name"], PROFILE)
    assert result["Full name"] == "Maria de Souza Pereira"


def test_full_name_variants():
    for label in ["Full Name *", "full name", "Your full name", "Nome completo"]:
        result = pre_populate_answers([label], PROFILE)
        assert result.get(label) == "Maria de Souza Pereira", f"{label!r} não preencheu"


def test_a_bare_name_label_is_the_full_name():
    """Ashby's application page asks for a single "Name" field. With no rule it
    went to the LLM, which answered "I DON'T KNOW — no basis in your profile"
    (ElevenLabs #6675, 2026-09-25). Reproduced 2026-09-29: the extractor returns
    the field every time; the miss was here."""
    for label in ["Name", "Name *", "*\nName", "Your name"]:
        answers = pre_populate_answers([label], PROFILE)
        assert answers.get(label) == "Maria de Souza Pereira", f"{label!r} was not filled"


def test_a_label_that_merely_starts_with_name_is_left_alone():
    for label in ["Name of your current employer", "Name pronunciation"]:
        assert label not in pre_populate_answers([label], PROFILE)


def test_full_name_does_not_shadow_first_or_last():
    """The full-name rule must not swallow the first/last labels it sits near."""
    result = pre_populate_answers(["First Name", "Last Name"], PROFILE)
    assert result["First Name"] == "Maria"
    assert result["Last Name"] == "de Souza Pereira"


def test_phone():
    result = pre_populate_answers(["Phone"], PROFILE)
    assert result["Phone"] == "11912345678"


def test_email():
    result = pre_populate_answers(["Email"], PROFILE)
    assert result["Email"] == "maria.pereira@example.com"


def test_linkedin():
    result = pre_populate_answers(["LinkedIn Profile"], PROFILE)
    assert result["LinkedIn Profile"] == "https://www.linkedin.com/in/mariapereira/"


def test_github():
    # A "Github" field became a gap on the live Resend form (2026-08-20):
    # linkedin and website had static rules, github never did.
    result = pre_populate_answers(["GitHub Profile"], PROFILE)
    assert result["GitHub Profile"] == "https://github.com/mariapereira"


def test_empty_profile_phone_not_included():
    result = pre_populate_answers(["Phone"], {})
    assert "Phone" not in result
