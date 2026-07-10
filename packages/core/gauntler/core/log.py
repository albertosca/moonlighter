import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_initialized = False
_DEFAULT_LOG_PATH = str(Path("~/.gauntler/app.log").expanduser())


def setup(log_path: str | None = None) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    resolved = log_path or _DEFAULT_LOG_PATH
    Path(resolved).parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("gauntler")
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

        rh = RichHandler(
            console=Console(stderr=True), level=logging.INFO, show_path=False,
            rich_tracebacks=False,
        )
        root.addHandler(rh)
    except ImportError:
        pass  # rich opcional


def get_logger(name: str) -> logging.Logger:
    if not _initialized:
        setup()
    return logging.getLogger(name)
