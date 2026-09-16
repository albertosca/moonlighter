"""moonlighter-scan: run a scan from a shell, no LLM conversation involved.

    moonlighter-scan [--keywords "..."] [--phase phase1|phase2|phase3|all] [--no-eval]
    moonlighter-scan --company SOURCE SLUG [--no-eval]

Prints one JSON document (scan_report_to_dict) on stdout; logs on stderr.
Exit 0 when jobs were evaluated, 1 when there was nothing new, 2 on an unknown
source or an invalid config. --no-eval parks new postings as needs_review
without spending a token; score them later with verify_job.
"""

import argparse
from typing import Any

from moonlighter.core.cli import EXIT_NOTHING, EXIT_OK, EXIT_USAGE, bootstrap, run
from moonlighter.core.llm import make_caller
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
    parser = argparse.ArgumentParser(
        prog="moonlighter-scan",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--keywords", default="", help="browser-scanner keywords (optional)")
    parser.add_argument("--phase", default="phase1", help="phase1 | phase2 | phase3 | all")
    parser.add_argument(
        "--company",
        nargs=2,
        metavar=("SOURCE", "SLUG"),
        help="scan one company's board instead of company_list.yaml",
    )
    parser.add_argument(
        "--no-eval", action="store_true", help="discover and persist, never call the LLM"
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
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
    import sys

    args = parse_args()
    sys.exit(run(lambda: _run(args)))
