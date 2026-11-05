"""The install diagnosis behind every slice's `doctor` command.

Where the state lives, whether the config loads, which slices are installed,
and what each missing one would add.
"""

from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

import yaml

from moonlighter.core.cli import EXIT_NOTHING, EXIT_OK
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.loading import load_config
from moonlighter.core.config.paths import moonlighter_home
from moonlighter.core.config.validation import validate_config
from moonlighter.core.db import db_path
from moonlighter.core.slices import Capability, capabilities, installed_slices, slices_to_install


def _capability_entry(capability: Capability) -> dict[str, Any]:
    return {
        "name": capability.name,
        "needs": sorted(capability.needs),
        "commands": list(capability.commands),
        "summary": capability.summary,
    }


def doctor_payload() -> tuple[dict[str, Any], int]:
    """Where the state lives and whether it loads.

    The diagnosis IS the payload -- a broken config is reported, not raised -- so a
    script can gate on the exit code and a human can read the JSON. Never calls
    bootstrap(): a broken install must still be diagnosable.
    """
    home = moonlighter_home()
    config_path = home / "config.yaml"
    valid, error = False, None
    try:
        validate_config(load_config())
        valid = True
    except (ConfigError, OSError, yaml.YAMLError) as failure:
        error = str(failure)
    installed = installed_slices()
    live, missing = capabilities(installed)
    payload = {
        "kind": "doctor",
        "home": str(home),
        "config": {
            "path": str(config_path),
            "exists": config_path.exists(),
            "valid": valid,
            "error": error,
        },
        "profile": {
            "path": str(home / "profile.yaml"),
            "exists": (home / "profile.yaml").exists(),
        },
        "db": {"path": db_path(), "exists": Path(db_path()).exists()},
        "slices": installed,
        "commands": sorted(
            entry_point.name
            for entry_point in entry_points(group="console_scripts")
            if entry_point.name.startswith("moonlighter")
        ),
        "capabilities": {
            "live": [_capability_entry(capability) for capability in live],
            "missing": [
                {
                    **_capability_entry(capability),
                    "needs_install": slices_to_install(capability, installed),
                }
                for capability in missing
            ],
        },
    }
    is_healthy = valid and config_path.exists()
    return payload, (EXIT_OK if is_healthy else EXIT_NOTHING)
