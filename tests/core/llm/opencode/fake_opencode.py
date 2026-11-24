"""A `create_subprocess_exec` stand-in for `opencode run` and `opencode session delete`."""

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

HANG = object()


@dataclass
class Launch:
    """One process the call started: its argv, launch options and what it got on stdin."""

    argv: tuple[str, ...]
    options: dict[str, Any]
    stdin: bytes | None = None


@dataclass
class FakeOpencode:
    """`run` prints `stdout`; `session delete` exits `delete_code` (or raises / hangs).

    `failed_starts` runs come first: each prints that output and exits 1.
    """

    stdout: bytes | object
    code: int = 0
    failed_starts: list[bytes] = field(default_factory=list)
    stderr: bytes = b""
    delete_code: int = 0
    delete_failure: BaseException | object | None = None
    launches: list[Launch] = field(default_factory=list)

    def _result(self, argv: tuple[str, ...]) -> tuple[bytes | object, bytes, int]:
        if argv[1] == "session":
            if isinstance(self.delete_failure, BaseException):
                raise self.delete_failure
            if self.delete_failure is HANG:
                return HANG, b"", 0
            return b"", b"session not found", self.delete_code
        if self.failed_starts:
            return self.failed_starts.pop(0), b"", 1
        return self.stdout, self.stderr, self.code

    async def create(self, *argv: str, **options: Any) -> MagicMock:
        launch = Launch(argv, options)
        self.launches.append(launch)
        stdout, stderr, code = self._result(argv)

        async def communicate(**keywords: Any) -> tuple[bytes, bytes]:
            launch.stdin = keywords.get("input")
            if stdout is HANG:
                await asyncio.Event().wait()
            assert isinstance(stdout, bytes)
            return stdout, stderr

        process = MagicMock()
        process.pid = 4242
        process.returncode = code
        process.communicate = communicate
        process.wait = AsyncMock(return_value=code)
        return process

    @property
    def run(self) -> Launch:
        return self.launches[0]

    @property
    def runs(self) -> list[Launch]:
        return [launch for launch in self.launches if launch.argv[1] == "run"]

    @property
    def deletes(self) -> list[Launch]:
        return [launch for launch in self.launches if launch.argv[1] == "session"]
