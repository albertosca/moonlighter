"""The compliance guard: declaration/conflict-of-interest questions never reach the LLM.

Provenance: live incident 2026-08-21 (gympass #3416) — the composer picked "I
currently hold or have previously held a position ... with a public body,
government entity, state-owned enterprise, political party, or international
organization" on a conflict-of-interest form, for a candidate who never held
any such position, in a field where the candidate certifies the information is
true. A signed false statement is a different class of failure from a weak
answer; these questions are deterministic-guard territory, like references,
salary and demographics.
"""

from moonlighter.application.answers.compliance import is_compliance_question

# The real option list from the gympass/Wellhub conflict-of-interest question.
GYMPASS_OPTIONS = (
    "I currently hold or have previously held a position, role, or affiliation "
    "with a public body, government entity, state-owned enterprise, political "
    "party, or international organization.",
    "I have a family member or close relationship with someone who holds or has "
    "held a position in a public body or government entity.",
    "I engage in external professional activity.",
    "I have nothing to declare.",
)


class TestLabelDetection:
    def test_conflict_of_interest_label(self):
        assert is_compliance_question("Conflict of Interest Declaration", ())

    def test_conflict_of_interest_label_pt(self):
        assert is_compliance_question("Declaração de conflito de interesse", ())

    def test_certification_label(self):
        assert is_compliance_question(
            "I certify that the information provided is true and complete", ()
        )

    def test_certification_label_pt(self):
        assert is_compliance_question("Certifico que as informações prestadas são verdadeiras", ())

    def test_criminal_record_label(self):
        assert is_compliance_question("Do you have a criminal record?", ())

    def test_criminal_record_label_pt(self):
        assert is_compliance_question("Possui antecedentes criminais?", ())

    def test_compliance_label(self):
        assert is_compliance_question("Compliance acknowledgement", ())


class TestOptionDetection:
    def test_the_live_gympass_options_trigger_under_a_neutral_label(self):
        # The real incident: the label itself was neutral; the options carried
        # the declaration content.
        assert is_compliance_question("Please select all that apply", GYMPASS_OPTIONS)

    def test_nothing_to_declare_option(self):
        assert is_compliance_question(
            "Anything we should know?", ("I have nothing to declare", "Other")
        )

    def test_nothing_to_declare_option_pt(self):
        assert is_compliance_question("Alguma observação?", ("Nada a declarar", "Outro"))

    def test_public_body_option(self):
        assert is_compliance_question(
            "Select your situation",
            ("I hold a position in a government entity", "None of the above"),
        )


class TestNonComplianceQuestionsPass:
    def test_technology_multi_select(self):
        assert not is_compliance_question(
            "Which technologies do you know?", ("Python", "Elixir", "React")
        )

    def test_english_level(self):
        assert not is_compliance_question(
            "English level",
            ("Fluent", "Advanced", "Intermediate", "Basic"),
        )

    def test_work_authorization_stays_on_its_own_track(self):
        # Eligibility questions are handled by the work-authorization rule in
        # field_map/work_auth; the compliance guard must not swallow them.
        assert not is_compliance_question(
            "Are you legally authorized to work in Brazil?", ("Yes", "No")
        )

    def test_sponsorship_stays_on_its_own_track(self):
        assert not is_compliance_question(
            "Will you now or in the future require sponsorship?", ("Yes", "No")
        )

    def test_plain_free_text(self):
        assert not is_compliance_question("Why do you want to work here?", ())

    def test_salary_expectation(self):
        assert not is_compliance_question("Salary expectation (BRL/month)", ())
