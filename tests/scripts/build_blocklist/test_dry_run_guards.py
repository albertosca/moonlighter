"""Pins the two dry-run guards one by one: a dry run neither collects a pattern nor saves one."""

import argparse
from unittest.mock import patch

import build_blocklist


def _forbidden(*_arguments, **_keywords):
    raise AssertionError("a dry run must not save")


def test_a_dry_run_report_collects_no_pattern_and_leaves_existing_alone(capsys):
    existing = {"old"}
    proposals = [{"pattern": " Intern ", "reasoning": "never senior"}]

    assert build_blocklist._report(proposals, existing, dry_run=True) == []

    assert existing == {"old"}
    assert (
        capsys.readouterr().out
        == "  + 'intern'                                 [DRY RUN]\n    → never senior\n"
    )


def test_a_dry_run_with_patterns_saves_nothing_and_says_so(capsys):
    arguments = argparse.Namespace(dry_run=True, yes=True)

    with (
        patch.object(build_blocklist, "save_learned", side_effect=_forbidden),
        patch.object(build_blocklist, "confirm_write", side_effect=_forbidden),
    ):
        build_blocklist._save_or_report(["intern"], arguments)

    assert capsys.readouterr().out == "No new patterns.\n"
