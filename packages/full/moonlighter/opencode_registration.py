"""Registering the moonlighter MCP server in opencode's global config: add, never rewrite."""

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# opencode 2.4.0's default handshake ("auto") fails against this server; the explicit
# protocol connects. `mcp.servers.<name>` is the canonical form: the flat
# `mcp.<name>` is normalized and loses `protocol`.
MCP_ENTRY: dict[str, Any] = {
    "type": "local",
    "command": ["uvx", "moonlighter"],
    "protocol": "2026-07-28",
}
_CANONICAL_MCP_KEYS = frozenset({"servers", "timeout"})
_SCHEMA = "https://opencode.ai/config.json"


@dataclass(frozen=True)
class Registration:
    written: bool
    path: Path
    reason: str


def opencode_config_path() -> Path:
    """The global config opencode reads: OPENCODE_CONFIG_DIR, then XDG_CONFIG_HOME, then ~/.config."""
    directory = os.environ.get("OPENCODE_CONFIG_DIR")
    if directory:
        return Path(directory).expanduser() / "opencode.json"
    xdg_config = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(xdg_config).expanduser() / "opencode" / "opencode.json"


def registration_snippet() -> str:
    return json.dumps({"mcp": {"servers": {"moonlighter": MCP_ENTRY}}}, indent=2)


def register_in_opencode(target: Path) -> Registration:
    """Add `mcp.servers.moonlighter` to `target`, or say why it was left alone."""
    jsonc = target.with_suffix(".jsonc")
    if jsonc.exists():
        return Registration(
            written=False,
            path=target,
            reason=f"{jsonc} exists, and moonlighter does not edit JSONC",
        )
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_json(target, {"$schema": _SCHEMA, "mcp": {"servers": {"moonlighter": MCP_ENTRY}}})
        return Registration(written=True, path=target, reason=f"created {target}")
    config, refusal = _existing_config(target)
    if config is None:
        return Registration(written=False, path=target, reason=refusal)
    backup = target.with_name(target.name + ".bak")
    shutil.copy2(target, backup)
    config.setdefault("mcp", {}).setdefault("servers", {})["moonlighter"] = MCP_ENTRY
    _write_json(target, config)
    return Registration(
        written=True,
        path=target,
        reason=f"added moonlighter to {target} (the previous file is {backup})",
    )


def _write_json(target: Path, config: dict[str, Any]) -> None:
    """Replace `target` in one step, so a crash never leaves half a config behind."""
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=target.parent, prefix=".opencode-", delete=False
    ) as staging:
        staging.write(json.dumps(config, indent=2) + "\n")
    Path(staging.name).replace(target)


def _existing_config(target: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        config = json.loads(target.read_bytes().decode("utf-8"))
    except OSError, ValueError:
        return None, f"{target} is not plain JSON (comments or trailing commas?)"
    if not isinstance(config, dict):
        return None, f"the top level of {target} is not an object"
    return _room_for_entry(config, target)


def _room_for_entry(config: dict[str, Any], target: Path) -> tuple[dict[str, Any] | None, str]:
    mcp = config.get("mcp", {})
    if not isinstance(mcp, dict) or not isinstance(mcp.get("servers", {}), dict):
        return None, f"`mcp` or `mcp.servers` in {target} is not an object"
    if "moonlighter" in mcp or "moonlighter" in mcp.get("servers", {}):
        return None, f"{target} already registers moonlighter; it was left as it is"
    if set(mcp) - _CANONICAL_MCP_KEYS:
        return None, f"{target} uses the older flat `mcp.<name>` form; add the entry by hand"
    return config, ""
