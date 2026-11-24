"""`opencode models` run under the call's isolation, for the startup check."""

import json
import signal
import stat
import subprocess
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

import pytest

from moonlighter.core.llm.opencode_models import list_opencode_models
from moonlighter.core.llm.opencode_profile import locked_config

POPEN = "moonlighter.core.llm.opencode_models.subprocess.Popen"
KILLPG = "moonlighter.core.llm.isolation.os.killpg"
LISTING = b"fake/echo\nopencode/big-pickle\n\nnoise\n"


class FakePopen:
    """Records how it was started and what the workdir held at that moment."""

    launches: ClassVar[list[FakePopen]] = []

    def __init__(self, argv: list[str], **options: Any) -> None:
        self.argv = argv
        self.options = options
        workdir = Path(options["cwd"])
        self.mode = stat.S_IMODE(workdir.stat().st_mode)
        self.config = json.loads((workdir / "opencode.json").read_text())
        self.pid = 4242
        self.returncode = self.code
        self.waits = 0
        FakePopen.launches.append(self)

    code = 0
    stdout = LISTING
    hangs = False

    def communicate(self, timeout: float | None = None) -> tuple[bytes, None]:
        self.waits += 1
        if self.hangs and timeout is not None:
            raise subprocess.TimeoutExpired(self.argv, timeout)
        return self.stdout, None


@pytest.fixture
def fake_popen():
    FakePopen.launches = []
    with patch(POPEN, FakePopen):
        yield FakePopen
    FakePopen.code, FakePopen.stdout, FakePopen.hangs = 0, LISTING, False


def test_the_listing_keeps_only_provider_model_lines(fake_popen):
    assert list_opencode_models("/opt/bin/opencode") == ["fake/echo", "opencode/big-pickle"]


def test_it_runs_standalone_in_a_private_locked_workdir_that_is_gone_afterwards(
    fake_popen, tmp_path
):
    list_opencode_models("/opt/bin/opencode")
    (launch,) = fake_popen.launches
    workdir = Path(launch.options["cwd"])
    assert launch.argv == ["/opt/bin/opencode", "models", "--standalone"]
    assert workdir.parent == tmp_path / "home"
    assert launch.mode == 0o700
    assert launch.config == locked_config()
    assert not workdir.exists()


def test_it_gets_the_locked_environment_and_its_own_group(fake_popen, monkeypatch):
    monkeypatch.setenv("OPENCODE_CONFIG", "/home/me/opencode.json")
    list_opencode_models("/opt/bin/opencode")
    (launch,) = fake_popen.launches
    environment = launch.options["env"]
    assert "OPENCODE_CONFIG" not in environment
    assert environment["OPENCODE_CONFIG_DIR"] == str(Path(launch.options["cwd"]) / "config")
    assert launch.options["start_new_session"] is True
    assert launch.options["stdin"] == subprocess.DEVNULL


def test_a_failed_listing_is_none(fake_popen):
    fake_popen.code = 1
    assert list_opencode_models("/opt/bin/opencode") is None


def test_a_binary_that_cannot_start_is_none_and_leaves_no_workdir(tmp_path):
    with patch(POPEN, side_effect=OSError("exec format error")):
        assert list_opencode_models("/opt/bin/opencode") is None
    assert list((tmp_path / "home").iterdir()) == []


def test_a_hung_listing_is_killed_with_its_group(fake_popen):
    fake_popen.hangs = True
    with patch(KILLPG) as killpg:
        assert list_opencode_models("/opt/bin/opencode") is None
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    (launch,) = fake_popen.launches
    assert launch.waits == 2  # the kill is reaped, so no zombie stays behind
    assert not Path(launch.options["cwd"]).exists()
