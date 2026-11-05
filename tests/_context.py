"""A stand-in FastMCP Context for tool tests."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from moonlighter.app_context import AppContext
from moonlighter.core.config.loading import load_config


def make_test_context(
    *,
    config: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    companies: dict[str, Any] | None = None,
    llm_caller: Any = None,
) -> SimpleNamespace:
    """Build a stand-in Context whose .request_context.lifespan_context is an AppContext.

    Tool tests pass context=make_test_context(...) instead of building the chain by hand.

    llm_caller defaults to a MagicMock, never None: the real server (server.lifespan)
    always hands the scan a real caller from make_caller(config), and --no-eval is
    the NO_EVAL marker of moonlighter.discovery.screening.no_eval, not None. A test that does
    not care about the caller (it patches evaluate_job / evaluate_jobs_batch directly)
    must still exercise the evaluated path.
    """
    app = AppContext(
        config=config if config is not None else load_config(),
        profile=profile if profile is not None else {},
        companies=companies if companies is not None else {},
        llm_caller=llm_caller if llm_caller is not None else MagicMock(),
        startup_warnings=[],
        permission_warnings=[],
    )
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app))
