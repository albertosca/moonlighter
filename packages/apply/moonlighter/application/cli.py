"""moonlighter-apply: prepare an application sheet from a shell.

    moonlighter-apply prepare JOB_ID              # questions from the job's ATS API
    moonlighter-apply prepare JOB_ID --paste FILE # questions read from a pasted page (- = stdin)
    moonlighter-apply prepare --url URL           # ingest the posting first (no LLM), then prepare
    moonlighter-apply prepare --url URL --company X --title Y  # non-ATS page: name it yourself
    moonlighter-apply doctor [--online]           # --online: request the CV header's links
    moonlighter-apply bootstrap-cv [--force] [--skip]

Prints one JSON document (sheet_result_to_dict) on stdout; logs on stderr.
Exit 0 when a sheet was produced, 1 when the job was not found, had no API
questions (paste the page), the pasted text had none, or --url's posting
could not be read; 2 on an invalid config.
"""

import argparse
import sys
from typing import Any

from moonlighter.application.commands.bootstrap_cv import run_bootstrap_cv
from moonlighter.application.commands.doctor import run_doctor
from moonlighter.application.commands.prepare import run_prepare
from moonlighter.application.cvgen.bootstrap_error import BootstrapError
from moonlighter.core.cli import JsonArgumentParser, bootstrap, run
from moonlighter.core.slices import slice_epilog

# A missing --paste path is a bad argument, not a crash -- run() maps it to
# exit 2 (usage_error) instead of exit 3 (a crash with a traceback the caller
# reads as "something broke").
USAGE_ERRORS = (FileNotFoundError,)

# An existing CV pool without --force is not a bug -- the CLI's own equivalent
# of the MCP tool's conversational "overwrite?" offer, just without
# anyone to ask: bootstrap_cv_pool refuses, and that refusal is an expected
# failure (exit 1), never a crash (exit 3).
EXPECTED_ERRORS = (BootstrapError,)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(
        prog="moonlighter-apply",
        description=__doc__,
        epilog=slice_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="compose the paste-ready sheet for one job")
    prepare.add_argument("job_id", type=int, nargs="?", help="a job already in the database")
    prepare.add_argument("--url", help="ingest this posting first (no LLM), then prepare it")
    prepare.add_argument(
        "--company", help="the posting's company, when --url is not on a known ATS"
    )
    prepare.add_argument("--title", help="the posting's title, when --url is not on a known ATS")
    prepare.add_argument(
        "--paste", metavar="FILE", help="page text to read questions from; - for stdin"
    )
    doctor = sub.add_parser(
        "doctor", help="where the state lives and whether the config loads, as JSON"
    )
    doctor.add_argument(
        "--online",
        action="store_true",
        help="also request every link in the CV templates' header; exit 1 if one is broken",
    )
    bootstrap_cv = sub.add_parser(
        "bootstrap-cv", help="draft a CV pool + template from profile.yaml"
    )
    bootstrap_cv.add_argument("--force", action="store_true", help="overwrite an existing pool")
    bootstrap_cv.add_argument(
        "--skip", action="store_true", help="decline the feature — never offered again, no LLM call"
    )
    arguments = parser.parse_args(argv)
    if arguments.command == "prepare" and (arguments.job_id is None) == (arguments.url is None):
        parser.error("prepare takes exactly one of JOB_ID or --url")
    if (
        arguments.command == "prepare"
        and arguments.url is None
        and (arguments.company or arguments.title)
    ):
        parser.error("--company and --title are only meaningful with --url")
    return arguments


async def _run(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if arguments.command == "doctor":
        return await run_doctor(arguments)
    config, profile = bootstrap()
    if arguments.command == "bootstrap-cv":
        return await run_bootstrap_cv(arguments, config, profile)
    return await run_prepare(arguments, config, profile)


def main() -> None:  # pragma: no cover - entry point (boundary)
    arguments = parse_args()
    sys.exit(run(lambda: _run(arguments), usage=USAGE_ERRORS, expected=EXPECTED_ERRORS))
