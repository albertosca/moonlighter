"""Which slices are installed, and what each one unlocks.

Detection is by installed DISTRIBUTION, never by import: importing a slice
from core would be the sideways dependency the whole design forbids. Install
a wheel and it is plugged in -- no config, no registry.
"""

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution

SLICES = ("scan", "apply", "email", "full")
DIST_NAMES = {
    "scan": "moonlighter-scan",
    "apply": "moonlighter-apply",
    "email": "moonlighter-email",
    "full": "moonlighter",
}


@dataclass(frozen=True)
class Capability:
    name: str
    needs: frozenset[str]
    commands: tuple[str, ...]
    summary: str


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        "discovery",
        frozenset({"scan"}),
        ("moonlighter-scan",),
        "scan company boards and portals, score postings, archive closed ones",
    ),
    Capability(
        "sheets",
        frozenset({"apply"}),
        ("moonlighter-apply prepare",),
        "compose a paste-ready application sheet, from a job id or straight from a URL",
    ),
    Capability(
        "tracking",
        frozenset({"email"}),
        ("moonlighter-email sync", "moonlighter-email register"),
        "register applications and match Gmail replies back to them",
    ),
    Capability(
        "scan-to-sheet",
        frozenset({"scan", "apply"}),
        (),
        "one script: scan, pick by score, prepare a sheet for each",
    ),
    Capability(
        "alias-round-trip",
        frozenset({"apply", "email"}),
        (),
        "the tracking alias a sheet mints is the one sync matches replies against",
    ),
    Capability(
        "mcp-server",
        frozenset({"full"}),
        ("moonlighter",),
        "the MCP server for Claude Code, plus answer-bank promotion when a reply advances an application",
    ),
)


def installed_slices() -> dict[str, bool]:
    out = {}
    for slice_name, dist_name in DIST_NAMES.items():
        try:
            distribution(dist_name)
            out[slice_name] = True
        except PackageNotFoundError:
            out[slice_name] = False
    return out


def capabilities(installed: dict[str, bool]) -> tuple[list[Capability], list[Capability]]:
    live = [c for c in CAPABILITIES if all(installed.get(s, False) for s in c.needs)]
    missing = [c for c in CAPABILITIES if c not in live]
    return live, missing


def slice_epilog(installed: dict[str, bool] | None = None) -> str:
    """The tail of every CLI's --help: what this install can do, and what each
    missing slice would add. Wording only -- the structure is the same on
    every combo."""
    installed = installed_slices() if installed is None else installed
    _live, missing = capabilities(installed)
    lines = ["installed: " + ", ".join(s for s in SLICES if installed.get(s, False))]
    for c in missing:
        need = ", ".join(sorted(c.needs - {s for s in SLICES if installed.get(s, False)}))
        cmds = f" ({', '.join(c.commands)})" if c.commands else ""
        lines.append(f"  install {need} -> would add: {c.name}{cmds} -- {c.summary}")
    return "\n".join(lines)
