import logging
from pathlib import Path


def test_get_logger_returns_logger_with_correct_name():
    from moonlighter.core.log import get_logger

    logger = get_logger("moonlighter.foo")
    assert logger.name == "moonlighter.foo"


def test_setup_creates_file_handler(tmp_path):
    from moonlighter.core import log as log_mod

    # reset module state to guarantee a clean setup
    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == log_path


def test_setup_idempotent(tmp_path):
    from moonlighter.core import log as log_mod

    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)
    log_mod.setup(log_path=log_path)  # second call

    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1  # did not duplicate


def test_log_message_reaches_file(tmp_path):
    from moonlighter.core import log as log_mod

    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    logger = log_mod.get_logger("moonlighter.test_write")
    logger.info("test message xyz")

    # flush and close handlers to guarantee the write
    for h in root.handlers:
        h.flush()

    content = Path(log_path).read_text()
    assert "test message xyz" in content


def test_setup_without_rich_falls_back_silently(tmp_path, monkeypatch):
    """rich absent → ImportError swallowed, only the FileHandler remains (log.py:35-36)."""
    import logging
    import sys

    from moonlighter.core import log as log_mod

    root = logging.getLogger("moonlighter")
    saved = root.handlers[:]
    monkeypatch.setattr(log_mod, "_initialized", False)
    monkeypatch.setitem(sys.modules, "rich.logging", None)  # import → ImportError
    try:
        log_mod.setup(log_path=str(tmp_path / "app.log"))
    finally:
        root.handlers[:] = saved  # restaura o logger global compartilhado


def test_setup_uses_rotating_file_handler(tmp_path):
    """S-07: app.log must rotate — was unbounded (3.4MB and growing in prod)."""
    from logging.handlers import RotatingFileHandler

    from moonlighter.core import log as log_mod

    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].maxBytes == 10_000_000
    assert handlers[0].backupCount == 3


def test_rich_handler_writes_to_stderr_not_stdout(tmp_path, capsys):
    """S-13: on a stdio MCP server, stdout IS the JSON-RPC channel — a log line
    at the wrong moment corrupts protocol framing. Nothing but the protocol may
    write to stdout."""
    from moonlighter.core import log as log_mod

    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "app.log")
    log_mod.setup(log_path=log_path)

    logger = log_mod.get_logger("moonlighter.stdout_test")
    logger.info("this must never reach stdout")

    captured = capsys.readouterr()
    assert "this must never reach stdout" not in captured.out
