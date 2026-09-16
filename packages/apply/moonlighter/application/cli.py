"""moonlighter-apply: prepare an application sheet from a shell.

    moonlighter-apply prepare JOB_ID              # questions from the job's ATS API
    moonlighter-apply prepare JOB_ID --paste FILE # questions read from a pasted page (- = stdin)

Prints one JSON document (sheet_result_to_dict) on stdout; logs on stderr.
Exit 0 when a sheet was produced, 1 when the job was not found, had no API
questions (paste the page), or the pasted text had none; 2 on an invalid config.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

from moonlighter.application.assisted.results import SheetKind, sheet_result_to_dict
from moonlighter.application.assisted.service import (
    prepare_application,
    prepare_application_from_paste,
)
from moonlighter.core.cli import EXIT_NOTHING, EXIT_OK, bootstrap, run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="moonlighter-apply",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="compose the paste-ready sheet for one job")
    prepare.add_argument("job_id", type=int)
    prepare.add_argument(
        "--paste", metavar="FILE", help="page text to read questions from; - for stdin"
    )
    return parser.parse_args(argv)


def _read_paste(source: str) -> str:
    return sys.stdin.read() if source == "-" else Path(source).read_text()


async def _run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    config, profile = bootstrap()
    if args.paste is not None:
        result = await prepare_application_from_paste(
            args.job_id, _read_paste(args.paste), config, profile
        )
    else:
        result = await prepare_application(args.job_id, config, profile)
    code = EXIT_OK if result.kind is SheetKind.SHEET else EXIT_NOTHING
    return sheet_result_to_dict(result), code


def main() -> None:  # pragma: no cover - entry point (boundary)
    args = parse_args()
    sys.exit(run(lambda: _run(args)))
