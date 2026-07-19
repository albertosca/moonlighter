"""Standalone scan runner — run a scan in a terminal and watch the colored logs live.

    uv run python scripts/scan.py --phase phase1 [--keywords "..."]

Mirrors the MCP scan_and_evaluate tool but runs in the foreground, so its stderr
is a TTY and the RichHandler colors the per-operation summary. (scan_and_evaluate
also archives stale jobs, same as the tool.)
"""

import argparse
import asyncio

from moonlighter.core.config import load_config, load_profile, validate_config
from moonlighter.core.db import init_db
from moonlighter.core.llm import make_caller
from moonlighter.core.log import setup as setup_logging
from moonlighter.core.metrics import operation_metrics
from moonlighter.discovery import service as scan_service


async def _run(keywords: str, phase: str) -> str:
    config = load_config()
    validate_config(config)
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = {}
    init_db()
    caller = make_caller(config)
    with operation_metrics("scan_and_evaluate"):
        return await scan_service.scan_and_evaluate(keywords, phase, config, profile, caller)


def main() -> None:  # pragma: no cover - entry point (boundary)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--keywords", default="", help="LinkedIn scanner keywords (optional)")
    parser.add_argument(
        "--phase",
        default="phase1",
        help="phase1 (default/BR), phase2 (remote-first global), phase3 (big techs), or all",
    )
    args = parser.parse_args()
    setup_logging()
    print(asyncio.run(_run(args.keywords, args.phase)))


if __name__ == "__main__":  # pragma: no cover
    main()
