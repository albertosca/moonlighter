"""The opencode the person runs, against the one moonlighter's call isolation was measured on."""

import subprocess
from unittest.mock import Mock

import pytest

from moonlighter.core.llm import opencode_version
from moonlighter.core.llm.opencode_version import version_drift

RUN = "moonlighter.core.llm.opencode_version.subprocess.run"


def _prints(monkeypatch, stdout: bytes, code: int = 0) -> Mock:
    run = Mock(return_value=subprocess.CompletedProcess([], code, stdout=stdout, stderr=b""))
    monkeypatch.setattr(RUN, run)
    return run


@pytest.mark.parametrize("printed", [b"opencode v2.4.0\n", b"2.4.7\n"])
def test_the_measured_minor_is_quiet(monkeypatch, printed):
    _prints(monkeypatch, printed)
    assert version_drift("/opt/bin/opencode") is None


@pytest.mark.parametrize(("printed", "shown"), [(b"opencode v2.5.0", "2.5.0"), (b"3.0.1", "3.0.1")])
def test_another_version_names_itself_and_the_measured_one(monkeypatch, printed, shown):
    _prints(monkeypatch, printed)
    message = version_drift("/opt/bin/opencode")
    assert message is not None
    assert shown in message
    assert "2.4" in message


def test_the_probe_is_bounded_and_reads_no_stdin(monkeypatch):
    run = _prints(monkeypatch, b"opencode v2.4.0")
    version_drift("/opt/bin/opencode")
    (argv,), options = run.call_args
    assert argv == ["/opt/bin/opencode", "--version"]
    assert options["timeout"] == opencode_version._VERSION_TIMEOUT_SECONDS
    assert options["stdin"] is subprocess.DEVNULL


@pytest.mark.parametrize("failure", [OSError("gone"), subprocess.TimeoutExpired(["opencode"], 10)])
def test_a_probe_that_fails_stays_quiet(monkeypatch, failure):
    monkeypatch.setattr(RUN, Mock(side_effect=failure))
    assert version_drift("/opt/bin/opencode") is None


@pytest.mark.parametrize(("printed", "code"), [(b"no version here", 0), (b"opencode v9.9.9", 1)])
def test_an_unreadable_or_failed_answer_stays_quiet(monkeypatch, printed, code):
    _prints(monkeypatch, printed, code)
    assert version_drift("/opt/bin/opencode") is None
