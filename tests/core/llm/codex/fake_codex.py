from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

LOGGED_IN = b"Logged in using ChatGPT\n"


def fake_process(stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> MagicMock:
    process = MagicMock()
    process.returncode = code
    process.pid = 4242
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.wait = AsyncMock(return_value=code)
    return process


def write_final_message(argv: tuple[str, ...], answer: str) -> None:
    """Write `answer` to the `--output-last-message` file, as the real CLI does."""
    Path(argv[argv.index("--output-last-message") + 1]).write_text(answer)


def fake_codex(
    answer: str | None, *, login: bytes = LOGGED_IN, login_code: int = 0, login_stderr: bytes = b""
):
    """create_subprocess_exec stand-in: `login status` first, then `exec`, which
    writes `answer` to the `--output-last-message` file the way the real CLI does.
    """
    calls: list[tuple[tuple[str, ...], dict]] = []
    processes: list[MagicMock] = []

    async def create(*argv: str, **launch_options):
        calls.append((argv, launch_options))
        if argv[1:3] == ("login", "status"):
            process = fake_process(login, login_stderr, login_code)
        else:
            if answer is not None:
                write_final_message(argv, answer)
            process = fake_process(b"", b"", 0)
        processes.append(process)
        return process

    return create, calls, processes
