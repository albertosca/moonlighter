"""Pins the --help text of build_blocklist: its docstring is the description and every flag is documented."""

import sys

import build_blocklist
import pytest


def test_help_text(monkeypatch, capsys, snapshot_text):
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(sys, "argv", ["build_blocklist.py", "--help"])

    with pytest.raises(SystemExit) as stopped:
        build_blocklist.main()

    assert stopped.value.code == 0
    snapshot_text(capsys.readouterr().out, "help")
