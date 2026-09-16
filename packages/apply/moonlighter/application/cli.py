"""moonlighter-apply: prepare an application sheet from a shell.

    moonlighter-apply prepare JOB_ID              # questions from the job's ATS API
    moonlighter-apply prepare JOB_ID --paste FILE # questions read from a pasted page (- = stdin)
    moonlighter-apply prepare --url URL           # ingest the posting first (no LLM), then prepare

Prints one JSON document (sheet_result_to_dict) on stdout; logs on stderr.
Exit 0 when a sheet was produced, 1 when the job was not found, had no API
questions (paste the page), the pasted text had none, or --url's posting
could not be read; 2 on an invalid config.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

from moonlighter.application.assisted.results import SheetKind, sheet_result_to_dict
from moonlighter.application.assisted.service import (
    failed_sheet,
    prepare_application,
    prepare_application_from_paste,
)
from moonlighter.core.cli import EXIT_NOTHING, EXIT_OK, JsonArgumentParser, bootstrap, run
from moonlighter.core.ingest import job_from_url

# A missing --paste path is a bad argument, not a crash -- run() maps it to
# exit 2 (usage_error) instead of exit 3 (a crash with a traceback the caller
# reads as "something broke").
USAGE_ERRORS = (FileNotFoundError,)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(
        prog="moonlighter-apply",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="compose the paste-ready sheet for one job")
    prepare.add_argument("job_id", type=int, nargs="?", help="a job already in the database")
    prepare.add_argument("--url", help="ingest this posting first (no LLM), then prepare it")
    prepare.add_argument(
        "--paste", metavar="FILE", help="page text to read questions from; - for stdin"
    )
    args = parser.parse_args(argv)
    if args.command == "prepare" and (args.job_id is None) == (args.url is None):
        parser.error("prepare takes exactly one of JOB_ID or --url")
    return args


def _read_paste(source: str) -> str:
    return sys.stdin.read() if source == "-" else Path(source).read_text()


async def _run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    config, profile = bootstrap()
    job_id = args.job_id
    if args.url is not None:
        job = await job_from_url(args.url)
        if job is None:
            failed = failed_sheet(
                SheetKind.POSTING_UNREADABLE,
                f"The posting at {args.url} could not be read. Paste the page with --paste, "
                "or add the job through the MCP server's add_job with company and title.",
                apply_url=args.url,
            )
            return sheet_result_to_dict(failed), EXIT_NOTHING
        job_id = job.id
    if args.paste is not None:
        result = await prepare_application_from_paste(
            job_id, _read_paste(args.paste), config, profile
        )
    else:
        result = await prepare_application(job_id, config, profile)
    code = EXIT_OK if result.kind is SheetKind.SHEET else EXIT_NOTHING
    return sheet_result_to_dict(result), code


def main() -> None:  # pragma: no cover - entry point (boundary)
    args = parse_args()
    sys.exit(run(lambda: _run(args), usage=USAGE_ERRORS))
