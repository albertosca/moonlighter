"""Sanitizing and registering the interview stages a reply proposes."""

from moonlighter.tracking.interview_stages import (
    _MAXIMUM_STAGES,
    _sanitize_stage,
    register_new_stage,
)


class TestSanitizeStage:
    def test_none_and_empty_return_none(self):
        assert _sanitize_stage(None) is None
        assert _sanitize_stage("") is None
        assert _sanitize_stage("   ") is None

    def test_normalizes_to_slug(self):
        assert _sanitize_stage("Technical Screen") == "technical_screen"
        assert _sanitize_stage("  Final   Round  ") == "final_round"

    def test_strips_disallowed_chars(self):
        # Injection payload collapses to an inert bounded slug.
        # Special chars like <>, {}, : are replaced with underscores; alphanumeric chars survive.
        assert _sanitize_stage("IGNORE ALL: <b>{instructions}</b>") == "ignore_all_b_instructions_b"

    def test_collapses_and_trims_underscores(self):
        assert _sanitize_stage("--a__b!!c--") == "a_b_c"

    def test_over_length_rejected(self):
        assert _sanitize_stage("x" * 41) is None

    def test_at_length_limit_accepted(self):
        assert _sanitize_stage("x" * 40) == "x" * 40

    def test_all_disallowed_returns_none(self):
        assert _sanitize_stage("!@#$%^&*()") is None


class TestRegisterNewStageBounds:
    def test_registers_sanitized_slug_not_raw(self):
        stages = ["applied"]
        email_config: dict = {}
        register_new_stage("Technical Screen", stages, email_config)
        assert stages == ["applied", "technical_screen"]
        assert email_config["interview_stages"] == ["applied", "technical_screen"]

    def test_rejects_unsanitizable(self):
        stages = ["applied"]
        email_config: dict = {}
        register_new_stage("!@#$", stages, email_config)
        assert stages == ["applied"]
        assert "interview_stages" not in email_config

    def test_does_not_duplicate_after_sanitize(self):
        stages = ["technical_screen"]
        email_config: dict = {}
        register_new_stage("Technical  Screen", stages, email_config)
        assert stages == ["technical_screen"]

    def test_count_cap_blocks_further_growth(self):
        stages = [f"s{index}" for index in range(_MAXIMUM_STAGES)]
        email_config: dict = {}
        register_new_stage("new-one", stages, email_config)
        assert len(stages) == _MAXIMUM_STAGES
        assert "new-one" not in stages
