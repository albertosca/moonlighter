"""setup() gives the moonlighter logger one rotating file handler on the path it is given, only once, and records reach that file; get_logger returns the logger it names."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from moonlighter.core import log as log_mod
from moonlighter.core.log import get_logger


def test_get_logger_returns_logger_with_correct_name():
    logger = get_logger("moonlighter.foo")
    assert logger.name == "moonlighter.foo"


def test_setup_creates_file_handler(tmp_path):
    # reset module state to guarantee a clean setup
    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    file_handlers = [
        handler for handler in root.handlers if isinstance(handler, logging.FileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == log_path


def test_setup_idempotent(tmp_path):
    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)
    log_mod.setup(log_path=log_path)  # second call

    file_handlers = [
        handler for handler in root.handlers if isinstance(handler, logging.FileHandler)
    ]
    assert len(file_handlers) == 1  # did not duplicate


def test_log_message_reaches_file(tmp_path):
    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    logger = log_mod.get_logger("moonlighter.test_write")
    logger.info("test message xyz")

    # flush and close handlers to guarantee the write
    for handler in root.handlers:
        handler.flush()

    content = Path(log_path).read_text()
    assert "test message xyz" in content


def test_setup_uses_rotating_file_handler(tmp_path):
    """S-07: app.log must rotate — was unbounded (3.4MB and growing in prod)."""
    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    handlers = [handler for handler in root.handlers if isinstance(handler, RotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].maxBytes == 10_000_000
    assert handlers[0].backupCount == 3
