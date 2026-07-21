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


def test_rich_handler_uses_vivid_level_styles(tmp_path):
    """The default rich theme (plain 'blue'/'yellow'/'green', no bold) reads as
    faint on a dark terminal — the operator's actual complaint. Levels must be
    bold/bright, distinct from rich's own DEFAULT_STYLES."""
    from moonlighter.core import log as log_mod
    from rich.default_styles import DEFAULT_STYLES
    from rich.logging import RichHandler

    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_mod.setup(log_path=str(tmp_path / "app.log"))
    rich_handlers = [h for h in root.handlers if isinstance(h, RichHandler)]
    assert len(rich_handlers) == 1
    console = rich_handlers[0].console
    for level in ("info", "warning", "error"):
        key = f"logging.level.{level}"
        assert str(console.get_style(key)) != str(DEFAULT_STYLES[key])


def test_metrics_highlighter_colors_op_summary_line():
    """op= observability lines (core/metrics.py) must stand out from ordinary
    log text — key=value pairs get their own styles instead of falling through
    ReprHighlighter's generic 'no style' default."""
    from moonlighter.core.log import MetricsHighlighter
    from rich.text import Text

    highlighter = MetricsHighlighter()
    text = Text("op=scan_and_evaluate calls=1 total_seconds=0.523 spend_limit_hits=0")
    highlighter.highlight(text)

    styled = {text.plain[s.start : s.end]: s.style for s in text.spans}
    assert styled.get("op=scan_and_evaluate") == "repr.op_name"
    assert styled.get("calls") == "repr.metric_key"
    assert styled.get("1") == "repr.metric_value"


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


def test_metrics_highlighter_colors_status_words_and_job_id():
    """Scanning a log line for outcome (filled/failed/skipped) and which job
    it's about (#2646) currently requires reading plain white text word by
    word — these get their own color so severity/outcome pop at a glance."""
    from moonlighter.core.log import MetricsHighlighter
    from rich.text import Text

    highlighter = MetricsHighlighter()
    text = Text("Job #2646: fill_form 3 filled, 1 failed:not_visible, 1 skipped")
    highlighter.highlight(text)

    styled = {text.plain[s.start : s.end]: s.style for s in text.spans}
    assert styled.get("#2646") == "repr.job_id"
    assert styled.get("filled") == "repr.status_ok"
    assert styled.get("failed:not_visible") == "repr.status_fail"
    assert styled.get("skipped") == "repr.status_attn"


def test_metrics_highlighter_status_words_need_word_boundary():
    """'fulfilled' must not light up as status_ok just because it contains
    the substring 'filled' — only the whole word counts as a status."""
    from moonlighter.core.log import MetricsHighlighter
    from rich.text import Text

    highlighter = MetricsHighlighter()
    text = Text("the request was fulfilled")
    highlighter.highlight(text)

    styled = {text.plain[s.start : s.end]: s.style for s in text.spans}
    assert "filled" not in styled
    assert "fulfilled" not in styled
