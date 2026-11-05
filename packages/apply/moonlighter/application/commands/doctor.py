"""The `doctor` subcommand: the install diagnosis, plus the CV header links with --online."""

import argparse
from typing import Any

import yaml

from moonlighter.application.cvgen.links import link_report
from moonlighter.core.cli import EXIT_NOTHING, EXIT_OK
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.loading import load_config
from moonlighter.core.doctor import doctor_payload


async def run_doctor(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """Return the doctor payload, never bootstrapping: a broken install must stay diagnosable."""
    payload, code = doctor_payload()
    if arguments.online:
        await _add_links(payload)
        if code == EXIT_OK and _has_broken_link(payload):
            code = EXIT_NOTHING
    return payload, code


async def _add_links(payload: dict[str, Any]) -> None:
    try:
        config = load_config()
    except (ConfigError, OSError, yaml.YAMLError) as error:
        # The payload from doctor_payload() already reports the broken config;
        # --online adds why the links were not checked, never a crash (exit 3).
        payload["links"] = None
        payload["links_error"] = f"config does not load: {error}"
        return
    payload["links"] = await link_report(config)
    if not payload["links"]:
        # An empty list read the same as "every link works".
        payload["links_note"] = (
            "no CV template with header links found in cv.template_dir; nothing checked"
        )


def _has_broken_link(payload: dict[str, Any]) -> bool:
    # links is None when the config did not load.
    return any(link["ok"] is False for link in payload["links"] or ())
