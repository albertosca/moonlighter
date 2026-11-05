"""Console lines start with a colored tag naming the moonlighter package that logged them, and carry no tag for a name outside the five packages."""

import logging

from moonlighter.core import log as log_mod
from moonlighter.core.log import _package_tag


def test_package_tag_maps_known_packages():
    assert _package_tag("moonlighter.discovery.evaluator") == "discovery"
    assert _package_tag("moonlighter.application.appliers.recruitee") == "application"
    assert _package_tag("moonlighter.core.browser") == "core"
    assert _package_tag("moonlighter.tracking.gmail_client") == "tracking"
    assert _package_tag("moonlighter.full.server") == "full"


def test_package_tag_returns_none_for_unknown_or_bare_name():
    """Defensive fallback: an unmapped package or a name with no
    'moonlighter.' prefix must not crash — just skip the prefix.
    """
    assert _package_tag("moonlighter.unknownpkg.mod") is None
    assert _package_tag("moonlighter") is None
    assert _package_tag("some_other_root.mod") is None


def test_package_rich_handler_prefixes_message_with_package_color(tmp_path):
    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    log_mod.setup(log_path=str(tmp_path / "app.log"))

    handlers = [
        handler for handler in root.handlers if isinstance(handler, log_mod._PackageRichHandler)
    ]
    assert len(handlers) == 1
    handler = handlers[0]

    record = logging.LogRecord(
        name="moonlighter.discovery.evaluator",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="scan complete",
        args=(),
        exc_info=None,
    )
    text = handler.render_message(record, "scan complete")

    assert text.plain.startswith("discovery")
    assert "scan complete" in text.plain
    assert text.spans[0].style == log_mod._PACKAGE_STYLES["discovery"]


def test_package_rich_handler_no_prefix_for_unmapped_package(tmp_path):
    """A logger name outside the 5 known packages (shouldn't happen in
    practice, but must degrade safely) renders with no prefix at all.
    """
    log_mod._initialized = False
    root = logging.getLogger("moonlighter")
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    log_mod.setup(log_path=str(tmp_path / "app.log"))
    handler = next(
        handler for handler in root.handlers if isinstance(handler, log_mod._PackageRichHandler)
    )

    record = logging.LogRecord(
        name="moonlighter.unknownpkg.mod",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    text = handler.render_message(record, "hello")
    assert text.plain == "hello"
