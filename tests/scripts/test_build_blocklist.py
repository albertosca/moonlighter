import argparse
from unittest.mock import patch

import build_blocklist


def _arguments(*, dry_run: bool, yes: bool) -> argparse.Namespace:
    return argparse.Namespace(threshold=3.0, company=None, dry_run=dry_run, yes=yes)


async def test_run_skips_write_without_confirmation(tmp_path, monkeypatch):
    """yes=False and the user declines -> blocklist_learned.yaml is never written."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    proposed = []

    async def fake_propose(company, prompt, *, caller, model):
        proposed.append(company)
        return [{"pattern": "recruiter", "examples": ["Recruiter"], "safe": True, "reasoning": "x"}]

    with (
        patch.object(build_blocklist, "fetch_low_scorers", return_value={"Acme": ["Recruiter"]}),
        patch.object(build_blocklist, "propose_for_company", new=fake_propose),
        patch.object(
            build_blocklist, "make_caller", return_value=lambda *_arguments, **_keywords: None
        ),
        patch("builtins.input", return_value="n"),
    ):
        await build_blocklist._run(
            _arguments(dry_run=False, yes=False), model="model", config={}, profile={}
        )

    assert proposed == ["Acme"]  # the fake was reached, so the missing file is a decision
    assert not (tmp_path / "blocklist_learned.yaml").exists()


async def test_run_writes_with_yes_flag_and_never_prompts(tmp_path, monkeypatch):
    """yes=True writes without EVER calling input() (non-interactive use)."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    async def fake_propose(company, prompt, *, caller, model):
        return [{"pattern": "recruiter", "examples": ["Recruiter"], "safe": True, "reasoning": "x"}]

    with (
        patch.object(build_blocklist, "fetch_low_scorers", return_value={"Acme": ["Recruiter"]}),
        patch.object(build_blocklist, "propose_for_company", new=fake_propose),
        patch.object(
            build_blocklist, "make_caller", return_value=lambda *_arguments, **_keywords: None
        ),
        patch("builtins.input", side_effect=AssertionError("must not prompt with --yes")),
    ):
        await build_blocklist._run(
            _arguments(dry_run=False, yes=True), model="model", config={}, profile={}
        )

    assert (tmp_path / "blocklist_learned.yaml").exists()


async def test_run_dry_run_never_prompts_either(tmp_path, monkeypatch):
    """--dry-run never writes or prompts, regardless of yes."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))

    proposed = []

    async def fake_propose(company, prompt, *, caller, model):
        proposed.append(company)
        return [{"pattern": "recruiter", "examples": ["Recruiter"], "safe": True, "reasoning": "x"}]

    with (
        patch.object(build_blocklist, "fetch_low_scorers", return_value={"Acme": ["Recruiter"]}),
        patch.object(build_blocklist, "propose_for_company", new=fake_propose),
        patch.object(
            build_blocklist, "make_caller", return_value=lambda *_arguments, **_keywords: None
        ),
        patch("builtins.input", side_effect=AssertionError("must not prompt on --dry-run")),
    ):
        await build_blocklist._run(
            _arguments(dry_run=True, yes=False), model="model", config={}, profile={}
        )

    assert proposed == ["Acme"]  # the fake was reached, so the missing file is a decision
    assert not (tmp_path / "blocklist_learned.yaml").exists()
