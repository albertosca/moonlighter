"""Every module inside packages/ gets its logger from the standard library.

`moonlighter.core.log.get_logger` runs `setup()` on first use, so importing a
module that called it at import time added handlers and created app.log as a
side effect. Every entry point (the four CLIs through `core.cli`, the MCP
server, the scripts) already calls `setup()` itself. `get_logger` stays only
for external plugins such as moonlighter-linkedin.
"""

import ast
from pathlib import Path
from typing import TypeIs

_PACKAGES_DIRECTORY = Path(__file__).resolve().parent.parent / "packages"
_DEFINING_MODULE = _PACKAGES_DIRECTORY / "core" / "moonlighter" / "core" / "log.py"


def _names_get_logger(node: ast.AST) -> TypeIs[ast.ImportFrom | ast.Name | ast.Attribute]:
    if isinstance(node, ast.ImportFrom):
        return any(alias.name == "get_logger" for alias in node.names)
    if isinstance(node, ast.Name | ast.Attribute):
        name = node.id if isinstance(node, ast.Name) else node.attr
        return name == "get_logger"
    return False


def test_no_package_module_uses_get_logger():
    offenders = sorted(
        f"{path.relative_to(_PACKAGES_DIRECTORY)}:{node.lineno}"
        for path in _PACKAGES_DIRECTORY.rglob("*.py")
        if path != _DEFINING_MODULE
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path)))
        if _names_get_logger(node)
    )
    assert offenders == []
