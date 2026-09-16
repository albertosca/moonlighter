"""What every moonlighter CLI shares: bootstrap, one JSON document on stdout,
semantic exit codes.

The contract (specs/2026-09-14-model-agnostic-cli-design.md): stdout carries
exactly one JSON document, always — including on failure — so a shell script
never has to parse prose; logs and warnings go to stderr; exit codes are
0 success, 1 expected failure, 2 usage error. `main()` in each slice's cli.py
is an untested boundary; everything it calls lives here or in that slice's
`_run`-style functions, which return (payload, code) and never print.
"""

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from moonlighter.core.config import (
    ConfigError,
    harden_permissions,
    load_config,
    load_profile,
    validate_config,
)
from moonlighter.core.db import Job, init_db
from moonlighter.core.log import setup as setup_logging

EXIT_OK = 0
EXIT_NOTHING = 1
EXIT_USAGE = 2

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


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def job_to_dict(job: Job) -> dict[str, Any]:
    """Every persisted column, datetimes as ISO-8601 strings."""
    return {column: _iso(getattr(job, column)) for column in _JOB_COLUMNS}


def emit(payload: dict[str, Any], code: int) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return code


def run(entry: Callable[[], Awaitable[tuple[dict[str, Any], int]]]) -> int:
    """Drive one CLI entry to its exit code. The only place a ConfigError is
    caught: it becomes the JSON document the contract promises, not a trace."""
    try:
        payload, code = asyncio.run(entry())
    except ConfigError as e:
        payload, code = {"kind": "config_error", "error": str(e)}, EXIT_USAGE
    return emit(payload, code)
