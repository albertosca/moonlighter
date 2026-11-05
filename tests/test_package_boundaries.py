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

_PACKAGES_DIRECTORY = Path(__file__).resolve().parent.parent / "packages"
_DISTRIBUTION_TO_DIRECTORY = {
    "moonlighter-core": "core",
    "moonlighter-scan": "scan",
    "moonlighter-apply": "apply",
    "moonlighter-email": "email",
}


def _package_directories() -> list[str]:
    return sorted(
        directory.name
        for directory in _PACKAGES_DIRECTORY.iterdir()
        if (directory / "pyproject.toml").exists()
    )


def _modules_provided_by(package_name: str) -> set[str]:
    """Every `moonlighter.*` module name the package's source tree ships."""
    root = _PACKAGES_DIRECTORY / package_name
    modules = set()
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).with_suffix("").parts
        module = ".".join(parts)
        modules.add(module.removesuffix(".__init__"))
    return modules


def _declared_moonlighter_dependencies(package_name: str) -> set[str]:
    """The sibling packages this one declares — as directory names."""
    data = tomllib.loads((_PACKAGES_DIRECTORY / package_name / "pyproject.toml").read_text())
    dependencies = data["project"].get("dependencies", [])
    found = set()
    for requirement in dependencies:
        name = requirement.split(">")[0].split("=")[0].split("<")[0].strip()
        if name in _DISTRIBUTION_TO_DIRECTORY:
            found.add(_DISTRIBUTION_TO_DIRECTORY[name])
    return found


def _moonlighter_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text())
    imports = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("moonlighter")
        ):
            imports.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            imports.extend(
                (node.lineno, alias.name)
                for alias in node.names
                if alias.name.startswith("moonlighter")
            )
    return imports


def _owner_by_module() -> dict[str, str]:
    """Map each module to the first package, in sorted order, that ships it."""
    owner: dict[str, str] = {}
    for package_name in _package_directories():
        for module in _modules_provided_by(package_name):
            owner.setdefault(module, package_name)
    return owner


def _shipping_package(imported: str, owner: dict[str, str]) -> str | None:
    """The package that ships `imported`, resolved to the most specific module any package ships.

    `moonlighter.core.db` and `moonlighter.views` both land here.
    """
    parts = imported.split(".")
    return next(
        (
            owner[".".join(parts[:prefix_length])]
            for prefix_length in range(len(parts), 0, -1)
            if ".".join(parts[:prefix_length]) in owner
        ),
        None,
    )


def _violations_of(package_name: str, owner: dict[str, str]) -> list[str]:
    """Every import in the package that reaches a package it does not declare."""
    allowed = {package_name} | _declared_moonlighter_dependencies(package_name)
    violations = []
    for path in (_PACKAGES_DIRECTORY / package_name).rglob("*.py"):
        for line_number, imported in _moonlighter_imports(path):
            source = _shipping_package(imported, owner)
            if source is not None and source not in allowed:
                relative_path = path.relative_to(_PACKAGES_DIRECTORY.parent)
                violations.append(
                    f"{relative_path}:{line_number} imports {imported} (ships in {source!r})"
                )
    return violations


def test_no_package_imports_from_a_package_it_does_not_declare():
    owner = _owner_by_module()
    violations = [
        violation
        for package_name in _package_directories()
        for violation in _violations_of(package_name, owner)
    ]

    assert violations == [], "undeclared cross-package imports:\n" + "\n".join(sorted(violations))
