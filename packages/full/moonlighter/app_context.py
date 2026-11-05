"""The MCP server's state, and the live re-read of config.yaml and profile.yaml on edit."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from mcp.server.mcpserver import Context

from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.loading import load_config
from moonlighter.core.config.validation import validate_config
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.dispatch import make_caller
from moonlighter.core.log import get_logger
from moonlighter.startup import StartupWarning

logger = get_logger(__name__)


def _modified_at(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


@dataclass
class WatchedFile:
    path: Path
    modified_at: int | None = field(init=False)

    def __post_init__(self) -> None:
        self.modified_at = _modified_at(self.path)

    def changed(self) -> bool:
        """True once per edit: the new modification time is recorded as read."""
        current = _modified_at(self.path)
        if current == self.modified_at:
            return False
        self.modified_at = current
        return True


@dataclass
class AppContext:
    config: dict[str, Any]
    profile: dict[str, Any]
    companies: dict[str, Any]
    llm_caller: LLMCaller
    startup_warnings: list[StartupWarning]
    permission_warnings: list[str]
    # Set by the lifespan only. config.yaml and profile.yaml used to be read once,
    # at connect time: on 2026-09-25 a config flag added mid-session was silently
    # ignored, and sync_email_responses marked 11 messages processed without
    # archiving them. A tool call now re-reads whichever file changed.
    config_file: WatchedFile | None = None
    profile_file: WatchedFile | None = None

    def refresh(self) -> None:
        """Re-read whichever of config.yaml and profile.yaml changed since the last call."""
        self._refresh_config()
        self._refresh_profile()

    def _refresh_config(self) -> None:
        if self.config_file is None or not self.config_file.changed():
            return
        try:
            _read_mapping(self.config_file.path)
            config = load_config(self.config_file.path)
            validate_config(config)
        except (ConfigError, OSError, yaml.YAMLError) as error:
            _keep_last_good("config.yaml", error)
        else:
            self.config = config
            self.llm_caller = make_caller(config)

    def _refresh_profile(self) -> None:
        if self.profile_file is None or not self.profile_file.changed():
            return
        if not self.profile_file.path.exists():
            # The server boots with {} when profile.yaml is absent, so a
            # deletion mid-session means the same thing.
            self.profile = {}
            return
        try:
            self.profile = _read_mapping(self.profile_file.path)
        except (ConfigError, OSError, yaml.YAMLError) as error:
            _keep_last_good("profile.yaml", error)


def _read_mapping(path: Path) -> dict[str, Any]:
    """The file's YAML mapping, or an error for anything else.

    An empty file is an error too: an editor that truncates before writing leaves
    one for a moment, and a tool call must not run on defaults in between
    (2026-09-29 review).
    """
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or not data:
        raise ConfigError(f"{path.name} is not a non-empty YAML mapping")
    return data


def _keep_last_good(name: str, error: Exception) -> None:
    logger.warning("%s changed but does not load (%s) — keeping the last good one", name, error)


def refreshed_app_context(context: Context[AppContext, Any]) -> AppContext:
    """The server's state, with config.yaml/profile.yaml re-read if edited."""
    app_context = context.request_context.lifespan_context
    app_context.refresh()
    return app_context
