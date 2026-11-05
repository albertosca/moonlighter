"""JsonArgumentParser answers a bad flag with one usage_error JSON line on stdout and leaves --help to argparse."""

import json

import pytest
from moonlighter.core.cli import JsonArgumentParser


def test_json_argument_parser_error_emits_usage_error_json_on_stdout_and_exits_2(capsys):
    # argparse's default .error() writes usage prose to stderr and NOTHING to
    # stdout -- a shell script that always parses stdout as JSON gets zero
    # bytes on a bad flag. JsonArgumentParser must still leave stdout carrying
    # exactly the contract's one JSON document.
    parser = JsonArgumentParser(prog="x")
    parser.add_argument("--flag")
    with pytest.raises(SystemExit) as exit_info:
        parser.parse_args(["--bogus"])
    assert exit_info.value.code == 2
    out, error_output = capsys.readouterr()
    assert out.endswith("\n")
    assert out.count("\n") == 1
    payload = json.loads(out)
    assert payload["kind"] == "usage_error"
    # argparse's own message names the unrecognized argument -- assert the
    # contract (kind + presence), not argparse's exact wording.
    assert "bogus" in payload["error"]
    assert error_output != ""  # usage prose still goes to stderr, unchanged


def test_json_argument_parser_help_still_exits_0_on_stdout(capsys):
    # --help must keep going through argparse's own default path (stdout,
    # exit 0) -- JsonArgumentParser only changes .error(), never .exit()/-h.
    parser = JsonArgumentParser(prog="x")
    with pytest.raises(SystemExit) as exit_info:
        parser.parse_args(["--help"])
    assert exit_info.value.code == 0
    out, _err = capsys.readouterr()
    assert "usage" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
