"""Re-import the server's own modules from scratch, leaving the cached ones back in place afterwards."""

import importlib
import sys
from types import ModuleType

import pytest

_PURGED = ("moonlighter.server", "moonlighter.app_context", "moonlighter.mcp_tools")


def import_server_afresh(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import `moonlighter.server` again, along with `app_context` and every `mcp_tools` module.

    A bare `sys.modules.pop` would leave the re-imported copy in `sys.modules` and as
    its parent's attribute (what `import moonlighter.server as server` resolves to) for
    every later test, so each purge goes through monkeypatch, which restores both.
    Purging only the server would leave the tool modules cached: a side effect at
    their import time would then go unseen.
    """
    cached = [
        name for name in sys.modules if name in _PURGED or name.startswith("moonlighter.mcp_tools.")
    ]
    parents = {name: sys.modules[name.rpartition(".")[0]] for name in cached}
    modules = {name: sys.modules[name] for name in cached}
    for name in cached:
        monkeypatch.setattr(parents[name], name.rpartition(".")[2], modules[name])
        monkeypatch.delitem(sys.modules, name)
    return importlib.import_module("moonlighter.server")
