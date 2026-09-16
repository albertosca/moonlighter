"""What every moonlighter CLI shares: bootstrap, one JSON document on stdout,
semantic exit codes.

The contract (specs/2026-09-14-model-agnostic-cli-design.md): stdout carries
exactly one JSON document, always — including on failure — so a shell script
never has to parse prose; logs and warnings go to stderr; exit codes are
0 success, 1 expected failure, 2 usage error, 3 unexpected crash. `main()` in
each slice's cli.py is an untested boundary; everything it calls lives here
or in that slice's `_run`-style functions, which return (payload, code) and
never print.
"""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, NoReturn

import yaml
from moonlighter.core.config import (
    ConfigError,
    harden_permissions,
    load_config,
    load_profile,
    moonlighter_home,
    validate_config,
)
from moonlighter.core.db import Job, _db_path, init_db
from moonlighter.core.log import setup as setup_logging
from moonlighter.core.slices import SLICES, capabilities, installed_slices

EXIT_OK = 0
EXIT_NOTHING = 1
EXIT_USAGE = 2
# A crash is neither an expected failure (1) nor a usage error (2) — a script
# consuming this CLI's JSON must be able to tell the three apart.
EXIT_CRASH = 3

_JOB_COLUMNS = (
    "id",
    "source",
    "company",
    "title",
    "url",
    "location",
    "remote_type",
    "description",
    "posted_at",
    "score",
    "score_notes",
    "caveats",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_source",
    "salary_notes",
    "status",
    "found_at",
    "closed_at",
)


class JsonArgumentParser(argparse.ArgumentParser):
    """An ArgumentParser whose .error() keeps the contract: stdout carries one
    JSON document even on a bad flag. Plain argparse writes usage prose to
    stderr and exits 2 with stdout untouched -- a shell script that always
    parses stdout as JSON gets zero bytes instead of a `usage_error` payload.
    --help is unaffected: it never calls .error(), so it keeps going through
    argparse's own default path (stdout, exit 0)."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        emit({"kind": "usage_error", "error": message}, EXIT_USAGE)
        sys.exit(EXIT_USAGE)


def bootstrap() -> tuple[dict[str, Any], dict[str, Any]]:
    """Same boot the MCP server does, minus the server: logging to stderr,
    config loaded and validated (ConfigError propagates — `run` turns it into
    JSON + exit 2), profile optional, DB schema ensured, permissions hardened
    with warnings on stderr. Startup checks (validate_startup) are deliberately
    absent: they live in moonlighter-full and are MCP-boot UX."""
    setup_logging()
    config = load_config()
    validate_config(config)
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = {}
    init_db()
    for warning in harden_permissions():
        print(f"⚠️  {warning}", file=sys.stderr, flush=True)
    return config, profile


def doctor_payload() -> tuple[dict[str, Any], int]:
    """Where the state lives and whether it loads. The diagnosis IS the
    payload -- a broken config is reported, not raised -- so a script can gate
    on the exit code and a human can read the JSON. Never calls bootstrap():
    a broken install must still be diagnosable."""
    home = moonlighter_home()
    config_path = home / "config.yaml"
    valid, error = False, None
    try:
        validate_config(load_config())
        valid = True
    except (ConfigError, OSError, yaml.YAMLError) as e:
        error = str(e)
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
        "db": {"path": _db_path(), "exists": Path(_db_path()).exists()},
        "slices": installed,
        "commands": sorted(
            ep.name
            for ep in entry_points(group="console_scripts")
            if ep.name.startswith("moonlighter")
        ),
        "capabilities": {
            "live": [
                {
                    "name": c.name,
                    "needs": sorted(c.needs),
                    "commands": list(c.commands),
                    "summary": c.summary,
                }
                for c in live
            ],
            "missing": [
                {
                    "name": c.name,
                    "needs": sorted(c.needs),
                    "commands": list(c.commands),
                    "summary": c.summary,
                    "needs_install": sorted(
                        c.needs - {s for s in SLICES if installed.get(s, False)}
                    ),
                }
                for c in missing
            ],
        },
    }
    ok = valid and config_path.exists()
    return payload, (EXIT_OK if ok else EXIT_NOTHING)


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def job_to_dict(job: Job) -> dict[str, Any]:
    """Every persisted column, datetimes as ISO-8601 strings."""
    return {column: _iso(getattr(job, column)) for column in _JOB_COLUMNS}


def emit(payload: dict[str, Any], code: int) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return code


def run(
    entry: Callable[[], Awaitable[tuple[dict[str, Any], int]]],
    *,
    expected: tuple[type[Exception], ...] = (),
    usage: tuple[type[Exception], ...] = (),
) -> int:
    """Drive one CLI entry to its exit code. ConfigError becomes the JSON
    document the contract promises, not a trace. `expected` and `usage` let a
    slice's cli.py classify its own routine exceptions -- a missing credential
    is not a bug (exit 1, `expected_failure`), a bad argument is not a crash
    (exit 2, `usage_error`) -- without core/cli.py importing or naming them.
    An empty tuple (the default) matches nothing, so `run(entry)` behaves
    exactly as before this existed. Anything left over is the same as always:
    the JSON is for the machine, the logged traceback is for the human."""
    try:
        payload, code = asyncio.run(entry())
    except ConfigError as e:
        payload, code = {"kind": "config_error", "error": str(e)}, EXIT_USAGE
    except usage as e:
        payload, code = (
            {"kind": "usage_error", "type": type(e).__name__, "error": str(e)},
            EXIT_USAGE,
        )
    except expected as e:
        payload, code = (
            {"kind": "expected_failure", "type": type(e).__name__, "error": str(e)},
            EXIT_NOTHING,
        )
    except Exception as e:
        logging.getLogger(__name__).exception("unhandled error in CLI entry")
        payload, code = (
            {
                "kind": "error",
                "type": type(e).__name__,
                "error": str(e),
            },
            EXIT_CRASH,
        )
    return emit(payload, code)
