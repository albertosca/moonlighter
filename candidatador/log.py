import logging
import os
from pathlib import Path

_initialized = False
_DEFAULT_LOG_PATH = os.path.expanduser("~/.candidatador/app.log")


def setup(log_path: str | None = None) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    resolved = log_path or _DEFAULT_LOG_PATH
    Path(resolved).parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("candidatador")
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)-45s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(resolved, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    try:
        from rich.logging import RichHandler
        rh = RichHandler(level=logging.INFO, show_path=False, rich_tracebacks=False)
        root.addHandler(rh)
    except ImportError:
        pass  # rich opcional


def get_logger(name: str) -> logging.Logger:
    if not _initialized:
        setup()
    return logging.getLogger(name)
