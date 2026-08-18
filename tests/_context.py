from types import SimpleNamespace
from typing import Any

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
