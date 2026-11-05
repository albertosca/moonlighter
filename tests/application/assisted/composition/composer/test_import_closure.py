"""Pins that importing the composer leaves the database layer unloaded."""

import subprocess
import sys


def test_importing_the_composer_does_not_pull_in_the_db_layer():
    # The plan's Global Constraint: compose_answers does no DB access, directly
    # or via import. The composer's modules take the bank's pure helpers from
    # bank/eligibility.py, never from bank/store.py, which imports
    # AnswerBankEntry at the top: importing it would drag in peewee and the
    # whole DB layer. Checked in a subprocess: this pytest session imported
    # both long ago.
    code = (
        "import sys, moonlighter.application.assisted.composition.composer as _;"
        "print('peewee' in sys.modules, 'moonlighter.core.db' in sys.modules)"
    )
    out = subprocess.run(  # noqa: S603 - literal argv, this interpreter, no shell
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    assert out.strip() == "False False"
