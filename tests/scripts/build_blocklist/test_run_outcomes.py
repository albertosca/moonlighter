"""Pins what build_blocklist prints and writes once the model has proposed patterns."""

import pytest

from tests.scripts.build_blocklist.harness import after_header, proposal, run_main, scored

HEADER = "Jobs to analyze: {titles} across {companies} company/ies  [threshold=3.0]\n\n"


def _seed_one_company():
    scored("Acme", "Recruiter Lead", 1.0)


def test_the_model_line_names_the_configured_model_and_the_learned_file(monkeypatch, home, capsys):
    run_main(monkeypatch, "--dry-run", config={"eval_model": "m-eval"})

    assert capsys.readouterr().out.startswith(
        f"Model: m-eval  |  blocklist_learned: {home}/blocklist_learned.yaml\n\n"
    )


def test_the_model_defaults_without_falling_back_to_llm_model(monkeypatch, home, capsys):
    run_main(monkeypatch, "--dry-run", config={"llm_model": "ignored"})

    assert capsys.readouterr().out.startswith("Model: claude-haiku-4-5-20251001  |  ")


def test_patterns_are_added_with_yes_and_saved_as_exact_yaml(monkeypatch, home, capsys):
    _seed_one_company()
    (home / "blocklist_learned.yaml").write_text("title_blocklist:\n- already\n")
    answers = {
        "Acme": [
            proposal("  New One ", reasoning="why one"),
            proposal("already", reasoning="old"),
            proposal("new one", reasoning="again"),
        ]
    }

    caller = run_main(monkeypatch, "--yes", answers=answers)

    assert after_header(capsys.readouterr().out) == (
        HEADER.format(titles=1, companies=1) + "▶ Acme (1 jobs)...\n"
        f"  + {'new one'!r:40s} [ADDED]\n"
        "    → why one\n"
        f"  + {'already'!r:40s} [ALREADY EXISTS]\n"
        "    → old\n"
        f"  + {'new one'!r:40s} [ALREADY EXISTS]\n"
        "    → again\n"
        "\n"
        "✓ 1 pattern(s) saved to blocklist_learned.yaml\n"
    )
    assert (home / "blocklist_learned.yaml").read_text() == (
        "title_blocklist:\n- already\n- new one\n"
    )
    assert [model for _, _, model in caller.calls] == ["m-eval"]


@pytest.mark.parametrize("flags", [("--dry-run",), ("--dry-run", "--yes")])
def test_a_dry_run_reports_no_new_patterns_and_never_writes(monkeypatch, home, capsys, *, flags):
    _seed_one_company()

    run_main(monkeypatch, *flags, answers={"Acme": [proposal("recruiter", reasoning="r")]})

    output = capsys.readouterr().out
    assert f"  + {'recruiter'!r:40s} [DRY RUN]\n    → r\n\nNo new patterns.\n" in output
    assert not (home / "blocklist_learned.yaml").exists()


@pytest.mark.parametrize("reply", ["y", "YES", " s ", "sim"])
def test_a_confirmation_saves(monkeypatch, home, capsys, *, reply):
    _seed_one_company()

    run_main(
        monkeypatch,
        answers={"Acme": [proposal("recruiter")]},
        confirm=lambda prompt: reply,
    )

    output = capsys.readouterr().out
    assert "\n1 new pattern(s) about to be saved:\n  - 'recruiter'\n" in output
    assert output.endswith("✓ 1 pattern(s) saved to blocklist_learned.yaml\n")
    assert (home / "blocklist_learned.yaml").read_text() == "title_blocklist:\n- recruiter\n"


@pytest.mark.parametrize("reply", ["", "n", "no", "maybe"])
def test_anything_but_yes_cancels_and_writes_nothing(monkeypatch, home, capsys, *, reply):
    _seed_one_company()
    prompts = []

    def confirm(prompt):
        prompts.append(prompt)
        return reply

    run_main(monkeypatch, answers={"Acme": [proposal("recruiter")]}, confirm=confirm)

    assert prompts == ["Confirm save? [y/N] "]
    assert capsys.readouterr().out.endswith("Cancelled — nothing was saved.\n")
    assert not (home / "blocklist_learned.yaml").exists()


def test_a_run_that_finds_nothing_new_never_asks(monkeypatch, home, capsys):
    _seed_one_company()

    run_main(monkeypatch, answers={"Acme": []})

    assert capsys.readouterr().out.endswith("(no safe pattern identified)\nNo new patterns.\n")
