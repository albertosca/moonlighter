"""setup()'s console handler uses bold, bright level styles, writes to stderr and never to stdout."""

import logging

from rich.default_styles import DEFAULT_STYLES
from rich.logging import RichHandler

from moonlighter.core import log as log_mod


def test_rich_handler_uses_vivid_level_styles(tmp_path):
    """The default rich theme (plain 'blue'/'yellow'/'green', no bold) reads as
    faint on a dark terminal — the operator's actual complaint. Levels must be
    bold/bright, distinct from rich's own DEFAULT_STYLES.
    """
    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    log_mod.setup(log_path=str(tmp_path / "app.log"))
    rich_handlers = [handler for handler in root.handlers if isinstance(handler, RichHandler)]
    assert len(rich_handlers) == 1
    console = rich_handlers[0].console
    for level in ("info", "warning", "error"):
        key = f"logging.level.{level}"
        assert str(console.get_style(key)) != str(DEFAULT_STYLES[key])


def test_rich_handler_writes_to_stderr_not_stdout(tmp_path, capsys):
    """S-13: on a stdio MCP server, stdout IS the JSON-RPC channel — a log line
    at the wrong moment corrupts protocol framing. Nothing but the protocol may
    write to stdout.
    """
    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    log_path = str(tmp_path / "app.log")
    log_mod.setup(log_path=log_path)

    logger = log_mod.get_logger("moonlighter.stdout_test")
    logger.info("this must never reach stdout")

    captured = capsys.readouterr()
    assert "this must never reach stdout" not in captured.out
