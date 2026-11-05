from unittest.mock import patch

import build_blocklist


def test_confirm_write_yes_returns_true():
    with patch("builtins.input", return_value="y"):
        assert build_blocklist._confirm_write(["recruiter"]) is True


def test_confirm_write_sim_returns_true():
    with patch("builtins.input", return_value="sim"):
        assert build_blocklist._confirm_write(["recruiter"]) is True


def test_confirm_write_empty_input_defaults_to_false():
    """S-10: silence is never consent — the default is 'no'."""
    with patch("builtins.input", return_value=""):
        assert build_blocklist._confirm_write(["recruiter"]) is False


def test_confirm_write_no_returns_false():
    with patch("builtins.input", return_value="n"):
        assert build_blocklist._confirm_write(["recruiter"]) is False


async def test_run_skips_write_without_confirmation(tmp_path, monkeypatch):
    """assume_yes=False and the user declines -> blocklist_learned.yaml is never written."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    async def fake_propose(company, titles, threshold, caller, model, profile):
        return [{"pattern": "recruiter", "examples": ["Recruiter"], "safe": True, "reasoning": "x"}]

    with (
        patch.object(build_blocklist, "_fetch_low_scorers", return_value={"Acme": ["Recruiter"]}),
        patch.object(build_blocklist, "_propose_for_company", new=fake_propose),
        patch.object(
            build_blocklist, "make_caller", return_value=lambda *_arguments, **_keywords: None
        ),
        patch("builtins.input", return_value="n"),
    ):
        await build_blocklist._run(3.0, None, False, "model", {}, {}, assume_yes=False)

    assert not (tmp_path / "blocklist_learned.yaml").exists()


async def test_run_writes_with_yes_flag_and_never_prompts(tmp_path, monkeypatch):
    """assume_yes=True writes without EVER calling input() (non-interactive use)."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    async def fake_propose(company, titles, threshold, caller, model, profile):
        return [{"pattern": "recruiter", "examples": ["Recruiter"], "safe": True, "reasoning": "x"}]

    with (
        patch.object(build_blocklist, "_fetch_low_scorers", return_value={"Acme": ["Recruiter"]}),
        patch.object(build_blocklist, "_propose_for_company", new=fake_propose),
        patch.object(
            build_blocklist, "make_caller", return_value=lambda *_arguments, **_keywords: None
        ),
        patch("builtins.input", side_effect=AssertionError("must not prompt with --yes")),
    ):
        await build_blocklist._run(3.0, None, False, "model", {}, {}, assume_yes=True)

    assert (tmp_path / "blocklist_learned.yaml").exists()


async def test_run_dry_run_never_prompts_either(tmp_path, monkeypatch):
    """--dry-run never writes or prompts, regardless of assume_yes."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    async def fake_propose(company, titles, threshold, caller, model, profile):
        return [{"pattern": "recruiter", "examples": ["Recruiter"], "safe": True, "reasoning": "x"}]

    with (
        patch.object(build_blocklist, "_fetch_low_scorers", return_value={"Acme": ["Recruiter"]}),
        patch.object(build_blocklist, "_propose_for_company", new=fake_propose),
        patch.object(
            build_blocklist, "make_caller", return_value=lambda *_arguments, **_keywords: None
        ),
        patch("builtins.input", side_effect=AssertionError("must not prompt on --dry-run")),
    ):
        await build_blocklist._run(3.0, None, True, "model", {}, {}, assume_yes=False)

    assert not (tmp_path / "blocklist_learned.yaml").exists()
