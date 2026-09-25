"""The MCP server answers the protocol over stdio, as a real client drives it.

Every other server test calls the tool functions directly, so a dependency bump
that breaks the stdio handshake left the whole suite green (found 2026-09-25,
only by a manual smoke). This starts the real entry point in a subprocess.
"""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

_SERVER = "from moonlighter.server import main; main()"
_ANSWER_TIMEOUT_SECONDS = 60


def _request(request_id: int, method: str, params: dict | None = None) -> bytes:
    message: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return (json.dumps(message) + "\n").encode()


def _read_answers(stdout, answers: dict, wanted: set, done: threading.Event) -> None:
    for line in stdout:
        message = json.loads(line)
        if message.get("id") in wanted:
            answers[message["id"]] = message
        if wanted <= answers.keys():
            done.set()
            return


def test_server_answers_initialize_and_lists_its_tools(tmp_path: Path):
    environment = {**os.environ, "MOONLIGHTER_HOME": str(tmp_path)}
    server = subprocess.Popen(  # noqa: S603 - literal argv, this interpreter
        [sys.executable, "-c", _SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    answers: dict = {}
    done = threading.Event()
    reader = threading.Thread(
        target=_read_answers, args=(server.stdout, answers, {1, 2}, done), daemon=True
    )
    reader.start()
    try:
        assert server.stdin is not None
        server.stdin.write(
            _request(
                1,
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            )
        )
        server.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        server.stdin.write(_request(2, "tools/list"))
        server.stdin.flush()
        assert done.wait(_ANSWER_TIMEOUT_SECONDS), f"no answer to { ({1, 2} - answers.keys()) }"
    finally:
        server.kill()
        server.wait()
    assert answers[1]["result"]["serverInfo"]["name"] == "moonlighter"
    tool_names = {tool["name"] for tool in answers[2]["result"]["tools"]}
    assert {"scan_and_evaluate", "prepare_application", "update_status"} <= tool_names
