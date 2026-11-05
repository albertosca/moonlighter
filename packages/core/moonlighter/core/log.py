"""Configures the moonlighter loggers once: a rotating log file and a colored stderr console."""

import logging
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar, cast, override

_initialized = False
_DEFAULT_LOG_PATH = str(Path("~/.moonlighter/app.log").expanduser())

# Rich's DEFAULT_STYLES for these keys are plain, unbolded colors (blue/yellow/
# green) that read as faint on a dark terminal. Bold + brighter variants make
# levels easy to spot at a glance; DEBUG stays de-emphasized on purpose (it's
# high-volume noise), everything else is meant to pop.
_VIVID_LEVEL_STYLES = {
    "logging.level.debug": "italic grey58",
    "logging.level.info": "bold bright_cyan",
    "logging.level.warning": "bold orange1",
    "logging.level.error": "bold bright_red",
    "logging.level.critical": "bold white on red",
    # MetricsHighlighter groups (see below): the op= observability summary line.
    "repr.op_name": "bold magenta",
    "repr.metric_key": "cyan",
    "repr.metric_value": "bright_yellow",
    # MetricsHighlighter groups: outcome words and job ids in ordinary messages.
    "repr.status_ok": "bold green3",
    "repr.status_fail": "bold red3",
    "repr.status_attn": "bold gold3",
    "repr.job_id": "bold blue",
}

# 5 real packages in the monorepo (packages/*/moonlighter/<this>). Colors
# deliberately outside the green/red/yellow/blue family already used by
# level and status highlighting, so the two color systems don't collide.
_PACKAGE_STYLES = {
    "core": "grey70",
    "discovery": "sea_green3",
    "application": "dodger_blue2",
    "tracking": "orchid",
    "full": "grey54",
}


def _package_tag(logger_name: str) -> str | None:
    """First dotted segment after 'moonlighter.', if it's one of the 5 known packages.

    None for the bare 'moonlighter' logger, an unprefixed name, or an unmapped package — callers
    must treat None as "no prefix".
    """
    remainder = logger_name.removeprefix("moonlighter.")
    if remainder == logger_name:
        return None
    package = remainder.split(".", 1)[0]
    return package if package in _PACKAGE_STYLES else None


try:
    from rich.highlighter import ReprHighlighter as _ReprHighlighter

    class MetricsHighlighter(_ReprHighlighter):
        """Highlights the op= observability summary lines emitted by core/metrics.py.

        Key=value pairs get their own styles instead of blending into ordinary log text.
        """

        highlights: ClassVar[Sequence[str]] = [
            *_ReprHighlighter.highlights,
            r"\b(?P<op_name>op=\S+)",
            (
                r"\b(?P<metric_key>calls|total_seconds|input_tokens|output_tokens|spend_limit_hits)="
                r"(?P<metric_value>\S+)"
            ),
            r"\b(?P<status_ok>filled|submitted|applied)\b",
            r"\b(?P<status_fail>failed(?::\w+)?)",
            r"\b(?P<status_attn>skipped|needs_review|unverified)\b",
            r"(?P<job_id>#\d+)",
        ]

    from rich.logging import RichHandler as _RichHandler
    from rich.text import Text as _Text

    class _PackageRichHandler(_RichHandler):
        """Prepends a colored package-name tag to every rendered message.

        The tag (core/discovery/application/tracking/full) is derived from the logger name, so log
        lines from different subsystems are visually grouped.
        """

        @override
        def render_message(self, record: logging.LogRecord, message: str) -> _Text:
            # RichHandler.render_message is annotated ConsoleRenderable; its body returns a Text.
            text = cast("_Text", super().render_message(record, message))
            package = _package_tag(record.name)
            if package is None:
                return text
            style = _PACKAGE_STYLES[package]
            return _Text.assemble((f"{package:<12}", style), text)

except ImportError:  # pragma: no cover - rich optional, mirrors setup()'s own guard
    pass


def setup(log_path: str | None = None) -> None:
    global _initialized  # noqa: PLW0603 - the once-per-process flag is module state that tests reset and read
    if _initialized:
        return
    _initialized = True

    resolved = log_path or _DEFAULT_LOG_PATH
    Path(resolved).parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("moonlighter")
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)-45s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # S-07: app.log ran with no rotation (3.4MB and growing in production) —
    # cap at 10MB x 3 backups.
    file_handler = RotatingFileHandler(
        resolved, maxBytes=10_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    try:
        from rich.console import Console  # noqa: PLC0415 - kept inside the ImportError guard; the rich-missing test blocks this import
        from rich.theme import Theme  # noqa: PLC0415 - kept inside the same ImportError guard as rich.console

        console_handler = _PackageRichHandler(
            console=Console(stderr=True, theme=Theme(_VIVID_LEVEL_STYLES)),
            level=logging.INFO,
            show_path=True,
            enable_link_path=False,
            rich_tracebacks=False,
            highlighter=MetricsHighlighter(),
        )
        root.addHandler(console_handler)
    except ImportError:
        pass  # rich optional


def get_logger(name: str) -> logging.Logger:
    if not _initialized:
        setup()
    return logging.getLogger(name)
