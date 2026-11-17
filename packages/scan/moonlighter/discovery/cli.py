"""moonlighter-scan: run a scan from a shell, no LLM conversation involved.

    moonlighter-scan [run] [--keywords "..."] [--phase phase1|phase2|phase3|all] [--no-eval]
    moonlighter-scan [run] --company SOURCE SLUG [--no-eval]
    moonlighter-scan add URL [--company C] [--title T] [--description D] [--track]
    moonlighter-scan doctor

`run` is implicit: no subcommand, or a leading flag, is a run -- the
long-standing grammar (`moonlighter-scan --no-eval | jq ...`) keeps working
unchanged. `add` and `doctor` are the only other words.

`add` scores and saves one posting from its URL, like the MCP add_job tool;
--track keeps a job you already chose as reviewed whatever its score. Prints
{"kind": "added" | "not_added", "message": ..., "job": ...}; exit 0 when the
job is in the database afterwards, 1 otherwise.

Prints one JSON document (scan_report_to_dict, or doctor_payload for
`doctor`) on stdout; logs on stderr. Exit 0 when jobs were evaluated, 1 when
there was nothing new, 2 on an unknown source or an invalid config. --no-eval
parks new postings as needs_review without spending a token; score them
later with verify_job.

Help for the run flags: `moonlighter-scan run --help`; the top-level `moonlighter-scan --help` also lists the installed slices.
"""

import argparse
import sys
from typing import Any

from moonlighter.core.cli import (
    EXIT_NOTHING,
    EXIT_OK,
    EXIT_USAGE,
    JsonArgumentParser,
    bootstrap,
    job_to_dict,
    run,
)
from moonlighter.core.db import Job
from moonlighter.core.doctor import doctor_payload
from moonlighter.core.llm.dispatch import make_caller
from moonlighter.core.slices import slice_epilog
from moonlighter.core.web.urls import normalize_job_url
from moonlighter.discovery.manual.jobs import add_job
from moonlighter.discovery.scan.results import ScanKind, ScanResult, scan_report_to_dict
from moonlighter.discovery.scan.scanning import scan_and_evaluate, scan_company
from moonlighter.discovery.screening.no_eval import NO_EVAL

_EXIT_BY_KIND = {
    ScanKind.EVALUATED: EXIT_OK,
    ScanKind.NO_NEW_JOBS: EXIT_NOTHING,
    ScanKind.ALL_KNOWN: EXIT_NOTHING,
    ScanKind.NO_OPEN_JOBS: EXIT_NOTHING,
    ScanKind.UNKNOWN_SOURCE: EXIT_USAGE,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `moonlighter-scan --no-eval` must keep working: with no subcommand, or a
    # leading flag, it is a run. `doctor` is the only other word. A bare
    # `-h`/`--help` as the first token is the one flag exempted: it must
    # reach the TOP-level parser (subcommands + epilog), not the run
    # subparser's own --help.
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help")):
        argv = ["run", *argv]
    parser = JsonArgumentParser(
        prog="moonlighter-scan",
        description=__doc__,
        epilog=slice_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="scan (the default when no subcommand is given)")
    run_parser.add_argument("--keywords", default="", help="browser-scanner keywords (optional)")
    run_parser.add_argument(
        "--phase",
        default="phase1",
        choices=("phase1", "phase2", "phase3", "all"),
        help="phase1 | phase2 | phase3 | all",
    )
    run_parser.add_argument(
        "--company",
        nargs=2,
        metavar=("SOURCE", "SLUG"),
        help="scan one company's board instead of company_list.yaml",
    )
    run_parser.add_argument(
        "--no-eval", action="store_true", help="discover and persist, never call the LLM"
    )
    add_parser = sub.add_parser("add", help="score and save one posting from its URL")
    add_parser.add_argument("url")
    add_parser.add_argument("--company", default="")
    add_parser.add_argument("--title", default="")
    add_parser.add_argument("--description", default="", help="fetched from the page when empty")
    add_parser.add_argument(
        "--track", action="store_true", help="keep it as reviewed whatever the score"
    )
    sub.add_parser("doctor", help="where the state lives and whether the config loads, as JSON")
    return parser.parse_args(argv)


async def _add(
    arguments: argparse.Namespace, config: dict[str, Any], profile: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    message = await add_job(
        arguments.url,
        arguments.company,
        arguments.title,
        arguments.description,
        config,
        profile,
        make_caller(config),
        track=arguments.track,
    )
    job = Job.get_or_none(Job.url == normalize_job_url(arguments.url))
    if job is None:
        return {"kind": "not_added", "message": message, "job": None}, EXIT_NOTHING
    return {"kind": "added", "message": message, "job": job_to_dict(job)}, EXIT_OK


async def _run(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if arguments.command == "doctor":
        return doctor_payload()
    config, profile = bootstrap()
    if arguments.command == "add":
        return await _add(arguments, config, profile)
    caller = NO_EVAL if arguments.no_eval else make_caller(config)
    report: ScanResult
    if arguments.company:
        source, slug = arguments.company
        report = await scan_company(source, slug, config, profile=profile, caller=caller)
    else:
        report = await scan_and_evaluate(
            arguments.keywords, arguments.phase, config, profile, caller
        )
    return scan_report_to_dict(report), _EXIT_BY_KIND[report.kind]


def main() -> None:  # pragma: no cover - entry point (boundary)
    arguments = parse_args()
    sys.exit(run(lambda: _run(arguments)))
