"""moonlighter-email: read application replies from a shell.

    moonlighter-email sync

Reads recent emails in the configured Gmail account, classifies them with the
LLM and advances the matching applications. Prints
{"kind": "synced", "updates": [...]} on stdout; exit 0 when anything was
updated, 1 when nothing was, 2 on an invalid config.

Standalone, this does NOT promote a newly advanced application's answers into
the shared answer bank: that bridge lives in the moonlighter-full server,
because moonlighter-email depends on moonlighter-core alone and may not import
the bank. A partial install has no bank to promote into; the full install runs
the same sync through the MCP tool and gets the promotion.
"""

import argparse
from typing import Any

from moonlighter.core.cli import EXIT_NOTHING, EXIT_OK, bootstrap, run
from moonlighter.core.llm import make_caller
from moonlighter.tracking.email_monitor import sync_responses


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="moonlighter-email",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="classify recent replies and advance applications")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    config, _profile = bootstrap()
    updates = await sync_responses(config, make_caller(config))
    return {"kind": "synced", "updates": updates}, (EXIT_OK if updates else EXIT_NOTHING)


def main() -> None:  # pragma: no cover - entry point (boundary)
    import sys

    args = parse_args()
    sys.exit(run(lambda: _run(args)))
