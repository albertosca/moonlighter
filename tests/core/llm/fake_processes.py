from unittest.mock import AsyncMock, MagicMock


def cursor_process(stdout: bytes = b"ok", stderr: bytes = b"", code: int = 0) -> MagicMock:
    mock_process = MagicMock()
    mock_process.returncode = code
    mock_process.communicate = AsyncMock(return_value=(stdout, stderr))
    return mock_process
