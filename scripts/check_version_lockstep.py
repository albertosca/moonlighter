"""Verifies all five package versions and the four ==pins in moonlighter-full
stay in lockstep — CLAUDE.md's own release note says this is bumped by hand
and "nothing in CI checks this". This is that check.

Usage:
    python scripts/check_version_lockstep.py
"""

import sys
import tomllib
from pathlib import Path

_SLUGS = ("core", "scan", "apply", "email", "full")
_PINNED_SLUGS = ("core", "scan", "apply", "email")  # full pins these four, not itself


def _version_of(repo_root: Path, slug: str) -> str:
    text = (repo_root / "packages" / slug / "pyproject.toml").read_text()
    return str(tomllib.loads(text)["project"]["version"])


def _pins_in_full(repo_root: Path) -> dict[str, str]:
    text = (repo_root / "packages" / "full" / "pyproject.toml").read_text()
    deps = tomllib.loads(text)["project"]["dependencies"]
    pins: dict[str, str] = {}
    for slug in _PINNED_SLUGS:
        name = f"moonlighter-{slug}"
        for dep in deps:
            if dep.startswith(f"{name}=="):
                pins[slug] = dep.split("==", 1)[1]
                break
    return pins


def check(repo_root: Path) -> list[str]:
    """Every mismatch found, as human-readable one-liners; [] when consistent."""
    versions = {slug: _version_of(repo_root, slug) for slug in _SLUGS}
    reference = versions["full"]
    mismatches = [
        f"packages/{slug}/pyproject.toml is at {versions[slug]}, expected {reference} (to match moonlighter-full)"
        for slug in _SLUGS
        if versions[slug] != reference
    ]
    pins = _pins_in_full(repo_root)
    mismatches += [
        f"packages/full/pyproject.toml pins moonlighter-{slug}=={pin}, expected =={reference}"
        for slug, pin in pins.items()
        if pin != reference
    ]
    return mismatches


def main(repo_root: Path) -> int:
    mismatches = check(repo_root)
    if not mismatches:
        print(f"Version lockstep is consistent at {_version_of(repo_root, 'full')}.")
        return 0
    print("Version lockstep broken:")
    for m in mismatches:
        print(f"  - {m}")
    return 1


if __name__ == "__main__":
    sys.exit(main(Path(__file__).resolve().parent.parent))
