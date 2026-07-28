"""Release-consistency checks over the five workspace distributions.

`moonlighter` pins its four siblings with `==`, so a release requires bumping
the version in five `pyproject.toml` files and four dependency pins at the same
time. PyPI validates dependency *format*, not *existence*: a partial bump
uploads cleanly and only fails later, at install time, on the user's machine.
These tests are the only thing standing between a forgotten bump and that
outcome.
"""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGES_DIR = REPO_ROOT / "packages"

# The distribution that pins the others. Its four `==` pins are what a partial
# bump breaks.
UMBRELLA = "moonlighter"

PIN_PATTERN = re.compile(r"^(?P<name>moonlighter[a-z-]*)\s*==\s*(?P<version>.+)$")


def _distributions() -> dict[str, dict]:
    """Map distribution name -> parsed pyproject, for every workspace package."""
    found = {}
    for pyproject in sorted(PACKAGES_DIR.glob("*/pyproject.toml")):
        data = tomllib.loads(pyproject.read_text())
        found[data["project"]["name"]] = data
    return found


def test_workspace_has_the_five_expected_distributions():
    # A sixth package, or a rename that misses this list, invalidates every
    # other assumption in this file -- including which one is the umbrella.
    assert set(_distributions()) == {
        "moonlighter",
        "moonlighter-core",
        "moonlighter-scan",
        "moonlighter-apply",
        "moonlighter-email",
    }


def test_all_distributions_share_one_version():
    versions = {name: data["project"]["version"] for name, data in _distributions().items()}
    assert len(set(versions.values())) == 1, (
        f"Versions drifted across the workspace: {versions}. All five must be bumped together."
    )


def test_umbrella_pins_match_the_shared_version():
    distributions = _distributions()
    expected = distributions[UMBRELLA]["project"]["version"]

    pins = {}
    for requirement in distributions[UMBRELLA]["project"]["dependencies"]:
        match = PIN_PATTERN.match(requirement.strip())
        if match:
            pins[match["name"]] = match["version"]

    siblings = set(distributions) - {UMBRELLA}
    assert set(pins) == siblings, (
        f"{UMBRELLA} must pin every sibling with `==`; "
        f"pinned {sorted(pins)}, siblings are {sorted(siblings)}."
    )
    assert set(pins.values()) == {expected}, (
        f"{UMBRELLA} is version {expected} but pins {pins}. "
        "The pins must be bumped with the versions."
    )
