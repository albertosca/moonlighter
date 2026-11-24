"""Registering the moonlighter MCP server in opencode's global config: add, never rewrite."""

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Measured on opencode 2.4.0. Its default handshake ("auto") fails against this
# server; the explicit protocol connects. By default it also hides MCP tools behind
# Code Mode's `execute`, so the model never sees `moonlighter_get_pipeline` and the
# rest; `codemode: false` offers them as tools, the way Claude Code does.
# `mcp.servers.<name>` is the canonical form: the flat `mcp.<name>` is normalized
# and loses `protocol`.
MCP_ENTRY: dict[str, Any] = {
    "type": "local",
    "command": ["uvx", "moonlighter"],
    "protocol": "2026-07-28",
    "codemode": False,
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
    try:
        return _register(target)
    except OSError as error:
        return Registration(written=False, path=target, reason=f"could not write {target}: {error}")


def _register(target: Path) -> Registration:
    # A config symlinked from a dotfiles repository is written through, so the link survives.
    real_file = target.resolve()
    if not real_file.exists():
        real_file.parent.mkdir(parents=True, exist_ok=True)
        _write_json(real_file, {"$schema": _SCHEMA, "mcp": {"servers": {"moonlighter": MCP_ENTRY}}})
        return Registration(written=True, path=target, reason=f"created {target}")
    config, refusal = _existing_config(target)
    if config is None:
        return Registration(written=False, path=target, reason=refusal)
    backup = _free_backup_path(target)
    shutil.copyfile(real_file, backup)
    config.setdefault("mcp", {}).setdefault("servers", {})["moonlighter"] = MCP_ENTRY
    _write_json(real_file, config)
    return Registration(
        written=True,
        path=target,
        reason=f"added moonlighter to {target} (the previous file is {backup})",
    )


def _free_backup_path(target: Path) -> Path:
    """`opencode.json.bak`, or the first `.bak.N` free: a backup the person kept is never replaced."""
    candidate = target.with_name(f"{target.name}.bak")
    number = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = target.with_name(f"{target.name}.bak.{number}")
        number += 1
    return candidate


def _write_json(real_file: Path, config: dict[str, Any]) -> None:
    """Replace `real_file` in one step, in its own mode, so a crash never leaves half a config."""
    descriptor, staging_name = tempfile.mkstemp(dir=real_file.parent, prefix=".opencode-")
    staged = Path(staging_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as staging:
            staging.write(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
        if real_file.exists():
            shutil.copymode(real_file, staged)
        staged.replace(real_file)
    except OSError:
        staged.unlink(missing_ok=True)
        raise


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
