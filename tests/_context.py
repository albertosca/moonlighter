from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from moonlighter.server import AppContext


def make_test_context(
    config: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    companies: dict[str, Any] | None = None,
    llm_caller: Any = None,
) -> SimpleNamespace:
    """Build a stand-in Context whose .request_context.lifespan_context is an AppContext.
    Tool tests pass ctx=make_test_context(...) instead of building the chain by hand."""
    from moonlighter.core.config import load_config

    app = AppContext(
        config=config if config is not None else load_config(),
        profile=profile if profile is not None else {},
        companies=companies if companies is not None else {},
        llm_caller=llm_caller,
        startup_warnings=[],
        permission_warnings=[],
    )
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app))


def make_applier_mock(base: Any = None) -> Any:
    """A test-double applier preset with sane BaseApplier hook defaults
    (not_applicable_reason -> None, prepare -> no-op).

    A bare, un-spec'd AsyncMock()/MagicMock() used as an applier stub silently
    mis-branches once these hooks are called unconditionally: an unconfigured
    AsyncMock()'s auto-generated attribute call is truthy (flips
    `if reason:` to the wrong branch), and a bare MagicMock()'s `.prepare()`
    isn't awaitable at all (TypeError, often masked by a broad `except
    Exception`). `spec=BaseApplier` does not fix this -- spec constrains
    attribute names, not return values. See
    docs/superpowers/plans/2026-07-23-linkedin-private-extraction.md's
    "Test-double landmine" backlog note.

    Pass `base=MagicMock()` for the confirm_apply-flavored call sites (which
    otherwise use a plain MagicMock); defaults to AsyncMock() for the
    apply_jobs-flavored ones. Both hooks are set regardless of which flow
    actually reads them -- harmless to over-set, and keeps this durably safe
    for whichever flow a future test exercises.
    """
    applier = base if base is not None else AsyncMock()
    applier.not_applicable_reason = AsyncMock(return_value=None)
    applier.prepare = AsyncMock()
    return applier
