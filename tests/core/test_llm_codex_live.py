"""Live sandbox canary for the Codex backend.

Deselected from the default suite (`-m 'not e2e'`). A skip is a failure when the
marker is selected, so a missing `codex` binary fails outright. Judged by side
effects: the agent's own account of what it did is not evidence, so the first
test runs plain shell probes under the exact permission profile the backend
passes, with no model involved.
"""

import http.server
import os
import secrets
import subprocess
import threading
from pathlib import Path

import pytest
from moonlighter.core.llm import _call_codex, _codex_permission_args, codex_executable

pytestmark = pytest.mark.e2e

CODEX_MODEL = os.environ.get("MOONLIGHTER_E2E_CODEX_MODEL", "gpt-6-luna")


def _require_codex() -> str:
    executable = codex_executable()
    if executable is None:
        pytest.fail(
            "the `codex` CLI was not found on PATH. "
            "Install the Codex CLI and run `codex login` with a ChatGPT account."
        )
    return executable


def _start_canary_server(request_log: list[str]) -> http.server.HTTPServer:
    class LoggingHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request_log.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"canary page")

        def log_message(self, format: str, *arguments: object) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), LoggingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_codex_profile_confines_reads_writes_and_network(tmp_path):
    executable = _require_codex()
    auth_file = Path.home() / ".codex" / "auth.json"
    assert auth_file.is_file(), "no ~/.codex/auth.json: log in, or the denial proves nothing"
    workspace = tmp_path.resolve() / "workspace"
    workspace.mkdir()
    (workspace / "inside.txt").write_text("inside")
    outside = tmp_path.resolve() / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text(secrets.token_hex(16))
    request_log: list[str] = []
    server = _start_canary_server(request_log)
    port = server.server_address[1]
    probe = (
        f"cat {workspace}/inside.txt >/dev/null; echo inside_read=$?; "
        f"cat {outside}/secret.txt >/dev/null 2>&1; echo outside_read=$?; "
        f"cat {auth_file} >/dev/null 2>&1; echo auth_read=$?; "
        f"ls {Path.home() / '.ssh'} >/dev/null 2>&1; echo ssh_list=$?; "
        f"touch {workspace}/written 2>/dev/null; echo write=$?; "
        f"/usr/bin/curl -s -m 3 http://127.0.0.1:{port}/ -o /dev/null; echo network=$?"
    )
    try:
        result = subprocess.run(  # noqa: S603 - argv built from the resolved codex binary and literals
            [executable, "sandbox", *_codex_permission_args(executable), "/bin/sh", "-c", probe],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        server.shutdown()
    outcomes = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if line.count("=") == 1
    )
    print(result.stdout, result.stderr)
    assert outcomes.get("inside_read") == "0", "positive control failed: the probe could not run"
    for denied in ("outside_read", "auth_read", "ssh_list", "write", "network"):
        assert outcomes.get(denied) not in (None, "0"), (denied, outcomes)
    assert not (workspace / "written").exists()
    assert request_log == [], request_log


async def test_codex_call_answers_and_leaves_no_trace_of_the_prompt(tmp_path, monkeypatch):
    _require_codex()
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    token = secrets.token_hex(16)
    answer = await _call_codex(
        f"Reply with the single word OK and nothing else.\nreference: {token}", CODEX_MODEL
    )
    print(answer)
    assert answer.strip(), "codex returned nothing: the run proves nothing"
    codex_home = Path.home() / ".codex"
    leaks = [
        path
        for path in codex_home.rglob("*")
        if path.is_file() and token.encode() in path.read_bytes()
    ]
    assert leaks == [], leaks
    assert not list((tmp_path / "home").glob("codex-*")), "the call workdir was not removed"
