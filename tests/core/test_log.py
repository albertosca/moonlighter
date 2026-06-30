import logging
from pathlib import Path


def test_get_logger_returns_logger_with_correct_name():
    from gauntler.core.log import get_logger

    logger = get_logger("gauntler.foo")
    assert logger.name == "gauntler.foo"


def test_setup_creates_file_handler(tmp_path):
    from gauntler.core import log as log_mod

    # reset estado do módulo para garantir setup limpo
    log_mod._initialized = False
    root = logging.getLogger("gauntler")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == log_path


def test_setup_idempotent(tmp_path):
    from gauntler.core import log as log_mod

    log_mod._initialized = False
    root = logging.getLogger("gauntler")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)
    log_mod.setup(log_path=log_path)  # segunda chamada

    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1  # não duplicou


def test_log_message_reaches_file(tmp_path):
    from gauntler.core import log as log_mod

    log_mod._initialized = False
    root = logging.getLogger("gauntler")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    logger = log_mod.get_logger("gauntler.test_write")
    logger.info("mensagem de teste xyz")

    # flush e fecha handlers para garantir escrita
    for h in root.handlers:
        h.flush()

    content = Path(log_path).read_text()
    assert "mensagem de teste xyz" in content


def test_setup_without_rich_falls_back_silently(tmp_path, monkeypatch):
    """rich ausente → ImportError engolido, só o FileHandler fica (log.py:35-36)."""
    import logging
    import sys

    from gauntler.core import log as log_mod

    root = logging.getLogger("gauntler")
    saved = root.handlers[:]
    monkeypatch.setattr(log_mod, "_initialized", False)
    monkeypatch.setitem(sys.modules, "rich.logging", None)  # import → ImportError
    try:
        log_mod.setup(log_path=str(tmp_path / "app.log"))
    finally:
        root.handlers[:] = saved  # restaura o logger global compartilhado
