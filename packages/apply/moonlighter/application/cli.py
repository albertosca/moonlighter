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
from pathlib import Path
from typing import Any

import yaml
from moonlighter.application.assisted.results import SheetKind, sheet_result_to_dict
from moonlighter.application.assisted.service import (
    failed_sheet,
    prepare_application,
    prepare_application_from_paste,
)
from moonlighter.application.cvgen.bootstrap import BootstrapError, bootstrap_cv_pool
from moonlighter.application.cvgen.links import link_report
from moonlighter.core.cli import (
    EXIT_NOTHING,
    EXIT_OK,
    JsonArgumentParser,
    bootstrap,
    doctor_payload,
    run,
)
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.loading import load_config
from moonlighter.core.ingest import job_from_url
from moonlighter.core.llm.dispatch import make_caller
from moonlighter.core.slices import slice_epilog

# A missing --paste path is a bad argument, not a crash -- run() maps it to
# exit 2 (usage_error) instead of exit 3 (a crash with a traceback the caller
# reads as "something broke").
USAGE_ERRORS = (FileNotFoundError,)

# An existing CV pool without --force is not a bug -- the CLI's own equivalent
# of the MCP tool's conversational "overwrite?" offer (Task 7), just without
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


def _read_paste(source: str) -> str:
    return sys.stdin.read() if source == "-" else Path(source).read_text()


async def _run(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if arguments.command == "doctor":
        payload, code = doctor_payload()
        if arguments.online:
            try:
                config = load_config()
            except (ConfigError, OSError, yaml.YAMLError) as error:
                # The payload above already reports the broken config; --online
                # adds why the links were not checked, never a crash (exit 3).
                payload["links"] = None
                payload["links_error"] = f"config does not load: {error}"
                return payload, code
            payload["links"] = await link_report(config)
            if not payload["links"]:
                # An empty list read the same as "every link works".
                payload["links_note"] = (
                    "no CV template with header links found in cv.template_dir; nothing checked"
                )
            if code == EXIT_OK and any(link["ok"] is False for link in payload["links"]):
                code = EXIT_NOTHING
        return payload, code
    config, profile = bootstrap()
    if arguments.command == "bootstrap-cv":
        if arguments.skip:
            from moonlighter.core.db import record_cv_bootstrap_decline

            record_cv_bootstrap_decline()
            return {"kind": "cv_bootstrap_skipped"}, EXIT_OK
        outcome = await bootstrap_cv_pool(
            profile, config, make_caller(config), force=arguments.force
        )
        return (
            {
                "kind": "cv_bootstrap",
                "pool_path": str(outcome.pool_path),
                "template_path": str(outcome.template_path),
                "pdf_path": str(outcome.pdf_path) if outcome.pdf_path else None,
                "bullet_count": outcome.bullet_count,
            },
            EXIT_OK,
        )
    job_id = arguments.job_id
    if arguments.url is not None:
        job = await job_from_url(arguments.url, company=arguments.company, title=arguments.title)
        if job is None:
            failed = failed_sheet(
                SheetKind.POSTING_UNREADABLE,
                f"The posting at {arguments.url} is not on a known ATS or could not be read. "
                "Pass --company and --title to ingest it anyway, or give a job id.",
                apply_url=arguments.url,
            )
            return sheet_result_to_dict(failed), EXIT_NOTHING
        job_id = job.id
    if arguments.paste is not None:
        result = await prepare_application_from_paste(
            job_id, _read_paste(arguments.paste), config, profile
        )
    else:
        result = await prepare_application(job_id, config, profile)
    code = EXIT_OK if result.kind is SheetKind.SHEET else EXIT_NOTHING
    return sheet_result_to_dict(result), code


def main() -> None:  # pragma: no cover - entry point (boundary)
    arguments = parse_args()
    sys.exit(run(lambda: _run(arguments), usage=USAGE_ERRORS, expected=EXPECTED_ERRORS))
