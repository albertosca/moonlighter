"""Pins the --help text of reevaluate_bug_victims: its docstring is the description and every flag is documented."""

import sys

import pytest
import reevaluate_bug_victims


def test_help_text(monkeypatch, capsys, snapshot_text):
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(sys, "argv", ["reevaluate_bug_victims.py", "--help"])

    with pytest.raises(SystemExit) as stopped:
        reevaluate_bug_victims.main()

    assert stopped.value.code == 0
    snapshot_text(capsys.readouterr().out, "help")
