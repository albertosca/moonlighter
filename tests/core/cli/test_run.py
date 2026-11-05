"""run turns an entry's result, or the exception it raises, into one JSON line on stdout and its exit code."""

import json

from moonlighter.core.cli import EXIT_CRASH, EXIT_NOTHING, EXIT_USAGE, run
from moonlighter.core.config.errors import ConfigError


async def _ok():
    return {"kind": "evaluated"}, 0


async def _config_broken():
    raise ConfigError("unknown config key 'nope'")


async def _crash():
    raise ValueError("boom")


def test_run_drives_the_entry_and_returns_its_exit_code(capsys):
    assert run(_ok) == 0
    assert json.loads(capsys.readouterr().out) == {"kind": "evaluated"}


def test_run_maps_a_config_error_to_json_on_stdout_and_exit_2(capsys):
    # The contract is JSON on stdout ALWAYS — a broken config must not turn
    # into a traceback on stderr that a script cannot parse.
    assert run(_config_broken) == EXIT_USAGE
    out = json.loads(capsys.readouterr().out)
    assert out == {"kind": "config_error", "error": "unknown config key 'nope'"}


def test_run_maps_an_unexpected_exception_to_json_on_stdout_and_exit_3(capsys, caplog):
    # Anything that isn't a ConfigError (a DB error, a plain bug) still has to
    # leave stdout as one parseable JSON document — never an empty stdout with
    # a traceback on stderr and Python's default exit code 1, which would
    # collide with EXIT_NOTHING without being a deliberate mapping.
    assert run(_crash) == EXIT_CRASH
    out = capsys.readouterr().out
    # stdout carries exactly the one JSON document and nothing else — no
    # traceback, no extra lines.
    assert out.endswith("\n")
    assert out.count("\n") == 1
    assert json.loads(out) == {"kind": "error", "type": "ValueError", "error": "boom"}
    # The human-facing half: the traceback/message still reaches the log.
    # (Not asserting stderr is otherwise empty: moonlighter.core.log.setup()
    # is a process-wide, once-only side effect that other tests in the suite
    # may already have triggered, which would make a real Rich handler write
    # to actual stderr here too — that's independent of this test's contract.)
    assert "boom" in caplog.text


class _NoToken(Exception):  # noqa: N818 - the payload's asserted "type" is this exact class name
    pass


class _BadArg(Exception):  # noqa: N818 - the payload's asserted "type" is this exact class name
    pass


async def _no_token():
    raise _NoToken("no token")


async def _bad_arg():
    raise _BadArg("bad path")


def test_run_classifies_an_expected_failure_as_exit_1_not_a_crash(capsys):
    # A routine, anticipated failure (missing credential, no data yet) is not
    # a bug: it must not land on EXIT_CRASH with a traceback the caller reads
    # as "something broke". expected= is how a slice's cli.py declares which
    # exceptions are routine for IT, without core/cli.py naming them.
    assert run(_no_token, expected=(_NoToken,)) == EXIT_NOTHING
    out = json.loads(capsys.readouterr().out)
    assert out == {"kind": "expected_failure", "type": "_NoToken", "error": "no token"}


def test_run_classifies_a_usage_error_as_exit_2(capsys):
    assert run(_bad_arg, usage=(_BadArg,)) == EXIT_USAGE
    out = json.loads(capsys.readouterr().out)
    assert out == {"kind": "usage_error", "type": "_BadArg", "error": "bad path"}


def test_run_usage_takes_priority_over_expected_when_both_match(capsys):
    # Order of clauses: ConfigError -> usage -> expected -> crash. A slice
    # could plausibly list the same exception type in both tuples; usage wins,
    # since it is checked first.
    assert run(_bad_arg, expected=(_BadArg,), usage=(_BadArg,)) == EXIT_USAGE
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "usage_error"


def test_run_default_expected_and_usage_are_empty_and_match_nothing(capsys):
    # An empty tuple in an except clause matches nothing -- run() with no
    # expected=/usage= behaves exactly as before this feature existed.
    assert run(_crash) == EXIT_CRASH
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "error"
