"""A local OpenAI-compatible endpoint for the opencode e2e tests: scripted replies, every body kept.

Nothing here reaches a real provider. opencode is pointed at it as a provider
`fake` with the model `echo`, so a test reads exactly what opencode would send.
"""

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any, Self, override

# Given the tool names a request offers, the tool to call and its JSON arguments, or
# None when the tool is not offered yet (opencode can send its first request before an
# MCP server connects): the fake answers 503, keeps the reply queued, and opencode retries.
ToolChooser = Callable[[list[str]], tuple[str, str] | None]
Message = tuple[dict[str, Any], str]


@dataclass(frozen=True)
class Reply:
    text: str = ""
    choose_tool: ToolChooser | None = None


def text(content: str) -> Reply:
    return Reply(text=content)


def tool_call(choose: ToolChooser) -> Reply:
    return Reply(choose_tool=choose)


def provider_config(base_url: str) -> dict[str, Any]:
    """The `providers.fake` block an `opencode.json` needs to reach this endpoint."""
    return {
        "fake": {
            "package": "@ai-sdk/openai-compatible",
            "settings": {"baseURL": base_url, "apiKey": "unused"},
            "models": {"echo": {"name": "echo"}},
        }
    }


def request_tool_names(body: dict[str, Any]) -> list[str]:
    return [tool["function"]["name"] for tool in body.get("tools") or []]


def _message(reply: Reply, body: dict[str, Any]) -> Message | None:
    """The assistant message for `reply` and its finish reason; None if its tool is missing."""
    if reply.choose_tool is None:
        return {"role": "assistant", "content": reply.text}, "stop"
    chosen = reply.choose_tool(request_tool_names(body))
    if chosen is None:
        return None
    name, arguments = chosen
    call = {"id": "call_1", "type": "function", "function": {"name": name, "arguments": arguments}}
    return {"role": "assistant", "content": None, "tool_calls": [call]}, "tool_calls"


def _streamed_chunks(message: dict[str, Any], finish_reason: str) -> list[dict[str, Any]]:
    delta = dict(message)
    for position, call in enumerate(delta.get("tool_calls") or []):
        call["index"] = position
    return [
        {"choices": [{"index": 0, "delta": delta}]},
        {
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    ]


class FakeProvider:
    """Serve `replies` in order, then repeat the last text reply; keep every POST body."""

    def __init__(self, replies: list[Reply]) -> None:
        self._replies = list(replies)
        self._fallback = next((reply for reply in reversed(replies) if not reply.choose_tool), None)
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        handler = type("Handler", (_Handler,), {"provider": self})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __enter__(self) -> Self:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._server.shutdown()
        self._server.server_close()

    def next_message(self, body: dict[str, Any]) -> Message | None:
        """Answer `body` with the next reply; None leaves that reply queued for the retry."""
        with self._lock:
            self.requests.append(body)
            reply = self._replies[0] if self._replies else self._fallback or text("")
            message = _message(reply, body)
            if message is not None and self._replies:
                self._replies.pop(0)
            return message


class _Handler(BaseHTTPRequestHandler):
    """One request to the fake; `provider` is set on the subclass `FakeProvider` builds."""

    provider: FakeProvider

    @override
    def log_message(self, format: str, *arguments: object) -> None:
        return

    def do_GET(self) -> None:
        self._send_json({"object": "list", "data": [{"id": "echo", "object": "model"}]})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        answer = self.provider.next_message(body)
        if answer is None:
            self._send_json({"error": {"message": "tool not offered yet"}}, status=503)
            return
        message, finish_reason = answer
        if body.get("stream"):
            self._send_stream(_streamed_chunks(message, finish_reason))
            return
        choice = {"index": 0, "message": message, "finish_reason": finish_reason}
        self._send_json({**_envelope("chat.completion"), "choices": [choice]})

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_stream(self, chunks: list[dict[str, Any]]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            payload = {**_envelope("chat.completion.chunk"), **chunk}
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


def _envelope(kind: str) -> dict[str, Any]:
    return {"id": "fake", "object": kind, "created": int(time.time()), "model": "echo"}
