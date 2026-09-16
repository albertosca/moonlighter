"""moonlighter-scan: run a scan from a shell, no LLM conversation involved.

    moonlighter-scan [run] [--keywords "..."] [--phase phase1|phase2|phase3|all] [--no-eval]
    moonlighter-scan [run] --company SOURCE SLUG [--no-eval]
    moonlighter-scan doctor

`run` is implicit: no subcommand, or a leading flag, is a run -- the
long-standing grammar (`moonlighter-scan --no-eval | jq ...`) keeps working
unchanged. `doctor` is the only other word.

Prints one JSON document (scan_report_to_dict, or doctor_payload for
`doctor`) on stdout; logs on stderr. Exit 0 when jobs were evaluated, 1 when
there was nothing new, 2 on an unknown source or an invalid config. --no-eval
parks new postings as needs_review without spending a token; score them
later with verify_job.
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
    doctor_payload,
    run,
)
from moonlighter.core.llm import make_caller
from moonlighter.core.slices import slice_epilog
from moonlighter.discovery.results import ScanKind, ScanReport, scan_report_to_dict
from moonlighter.discovery.service import scan_and_evaluate, scan_company

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
    sub.add_parser("doctor", help="where the state lives and whether the config loads, as JSON")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.command == "doctor":
        return doctor_payload()
    config, profile = bootstrap()
    caller = None if args.no_eval else make_caller(config)
    report: ScanReport
    if args.company:
        source, slug = args.company
        report = await scan_company(source, slug, config, profile, caller)
    else:
        report = await scan_and_evaluate(args.keywords, args.phase, config, profile, caller)
    return scan_report_to_dict(report), _EXIT_BY_KIND[report.kind]


def main() -> None:  # pragma: no cover - entry point (boundary)
    args = parse_args()
    sys.exit(run(lambda: _run(args)))
