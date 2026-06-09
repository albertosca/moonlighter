import logging
import pytest


def test_get_logger_returns_logger_with_correct_name():
    from candidatador.log import get_logger
    logger = get_logger("candidatador.foo")
    assert logger.name == "candidatador.foo"


def test_setup_creates_file_handler(tmp_path):
    from candidatador import log as log_mod
    # reset estado do módulo para garantir setup limpo
    log_mod._initialized = False
    root = logging.getLogger("candidatador")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == log_path


def test_setup_idempotent(tmp_path):
    from candidatador import log as log_mod
    log_mod._initialized = False
    root = logging.getLogger("candidatador")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)
    log_mod.setup(log_path=log_path)  # segunda chamada

    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1  # não duplicou


def test_log_message_reaches_file(tmp_path):
    from candidatador import log as log_mod
    log_mod._initialized = False
    root = logging.getLogger("candidatador")
    for h in root.handlers[:]:
        root.removeHandler(h)

    log_path = str(tmp_path / "test.log")
    log_mod.setup(log_path=log_path)

    logger = log_mod.get_logger("candidatador.test_write")
    logger.info("mensagem de teste xyz")

    # flush e fecha handlers para garantir escrita
    for h in root.handlers:
        h.flush()

    content = open(log_path).read()
    assert "mensagem de teste xyz" in content
