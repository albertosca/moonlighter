import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

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


try:
    from rich.highlighter import ReprHighlighter as _ReprHighlighter

    class MetricsHighlighter(_ReprHighlighter):
        """Highlights the op= observability summary lines emitted by
        core/metrics.py — key=value pairs get their own styles instead of
        blending into ordinary log text."""

        highlights = [  # noqa: RUF012 - mirrors ReprHighlighter's own class attr
            *_ReprHighlighter.highlights,
            r"\b(?P<op_name>op=\S+)",
            r"\b(?P<metric_key>calls|total_seconds|input_tokens|output_tokens|spend_limit_hits)="
            r"(?P<metric_value>\S+)",
            r"\b(?P<status_ok>filled|submitted|applied)\b",
            r"\b(?P<status_fail>failed(?::\w+)?)",
            r"\b(?P<status_attn>skipped|needs_review|unverified)\b",
            r"(?P<job_id>#\d+)",
        ]
except ImportError:  # pragma: no cover - rich optional, mirrors setup()'s own guard
    pass


def setup(log_path: str | None = None) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    resolved = log_path or _DEFAULT_LOG_PATH
    Path(resolved).parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("moonlighter")
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)-45s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # S-07: app.log ran with no rotation (3.4MB and growing in production) —
    # cap at 10MB x 3 backups.
    fh = RotatingFileHandler(resolved, maxBytes=10_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    try:
        from rich.console import Console
        from rich.logging import RichHandler
        from rich.theme import Theme

        rh = RichHandler(
            console=Console(stderr=True, theme=Theme(_VIVID_LEVEL_STYLES)),
            level=logging.INFO,
            show_path=True,
            enable_link_path=False,
            rich_tracebacks=False,
            highlighter=MetricsHighlighter(),
        )
        root.addHandler(rh)
    except ImportError:
        pass  # rich optional


def get_logger(name: str) -> logging.Logger:
    if not _initialized:
        setup()
    return logging.getLogger(name)
