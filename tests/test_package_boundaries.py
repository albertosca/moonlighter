"""Every package may only import from packages it actually declares.

This is not style. `moonlighter-scan` is published to PyPI on its own, and a
`pip install moonlighter-scan` gets exactly the dependencies its pyproject.toml
names. An import reaching into a package that is not declared there resolves
fine in this monorepo — every package is installed in the dev environment — and
raises ModuleNotFoundError at import time for the user who installed one slice.

Measured 2026-09-14 against the real published artifact:

    $ uv run --isolated --no-project --python 3.14 --with moonlighter-scan \\
        python -c "import moonlighter.discovery.service"
    ModuleNotFoundError: No module named 'moonlighter.views'

The allowed set is read from each package's own pyproject.toml rather than
hardcoded here, so this test cannot drift away from what the packages declare.
"""

import ast
import tomllib
from pathlib import Path

_PACKAGES_DIR = Path(__file__).resolve().parent.parent / "packages"
_DIST_TO_DIR = {
    "moonlighter-core": "core",
    "moonlighter-scan": "scan",
    "moonlighter-apply": "apply",
    "moonlighter-email": "email",
}


def _package_dirs() -> list[str]:
    return sorted(p.name for p in _PACKAGES_DIR.iterdir() if (p / "pyproject.toml").exists())


def _modules_provided_by(pkg: str) -> set[str]:
    """Every `moonlighter.*` module name the package's source tree ships."""
    root = _PACKAGES_DIR / pkg
    modules = set()
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).with_suffix("").parts
        module = ".".join(parts)
        modules.add(module.removesuffix(".__init__") if module.endswith("__init__") else module)
    return modules


def _declared_moonlighter_deps(pkg: str) -> set[str]:
    """The sibling packages this one declares — as directory names."""
    data = tomllib.loads((_PACKAGES_DIR / pkg / "pyproject.toml").read_text())
    deps = data["project"].get("dependencies", [])
    found = set()
    for raw in deps:
        name = raw.split(">")[0].split("=")[0].split("<")[0].strip()
        if name in _DIST_TO_DIR:
            found.add(_DIST_TO_DIR[name])
    return found


def _moonlighter_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text())
    out = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("moonlighter")
        ):
            out.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            out.extend(
                (node.lineno, alias.name)
                for alias in node.names
                if alias.name.startswith("moonlighter")
            )
    return out


def test_no_package_imports_from_a_package_it_does_not_declare():
    owner = {}
    for pkg in _package_dirs():
        for module in _modules_provided_by(pkg):
            owner.setdefault(module, pkg)

    violations = []
    for pkg in _package_dirs():
        allowed = {pkg} | _declared_moonlighter_deps(pkg)
        for path in (_PACKAGES_DIR / pkg).rglob("*.py"):
            for lineno, imported in _moonlighter_imports(path):
                parts = imported.split(".")
                # Resolve to the most specific module any package actually ships;
                # `moonlighter.core.db` and `moonlighter.views` both land here.
                source = next(
                    (
                        owner[".".join(parts[:i])]
                        for i in range(len(parts), 0, -1)
                        if ".".join(parts[:i]) in owner
                    ),
                    None,
                )
                if source is not None and source not in allowed:
                    rel = path.relative_to(_PACKAGES_DIR.parent)
                    violations.append(f"{rel}:{lineno} imports {imported} (ships in {source!r})")

    assert violations == [], "undeclared cross-package imports:\n" + "\n".join(sorted(violations))
