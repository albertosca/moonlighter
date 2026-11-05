"""moonlighter-email: read application replies from a shell.

    moonlighter-email sync
    moonlighter-email register JOB_ID
    moonlighter-email doctor

`sync` reads recent emails in the configured Gmail account, classifies them
with the LLM and advances the matching applications. Prints
{"kind": "synced", "updates": [...]} on stdout; exit 0 when anything was
updated, 1 when nothing was, 2 on an invalid config.

Standalone, this does NOT promote a newly advanced application's answers into
the shared answer bank: that bridge lives in the moonlighter-full server,
because moonlighter-email depends on moonlighter-core alone and may not import
the bank. A partial install has no bank to promote into; the full install runs
the same sync through the MCP tool and gets the promotion.

`register JOB_ID` marks a job as applied by hand and mints its +ref tracking
alias, using only moonlighter-core models -- so it works the same in a
standalone email install. Exit 0 (kind "registered") when the job exists,
1 (kind "job_not_found") when it doesn't.
"""

import argparse
import sys
from typing import Any

from moonlighter.core.cli import (
    EXIT_NOTHING,
    EXIT_OK,
    JsonArgumentParser,
    bootstrap,
    run,
)
from moonlighter.core.doctor import doctor_payload
from moonlighter.core.llm.dispatch import make_caller
from moonlighter.core.slices import slice_epilog
from moonlighter.tracking.gmail.client import GmailAuthError
from moonlighter.tracking.register import RegisterKind, register_application, register_to_dict
from moonlighter.tracking.sync.monitor import sync_responses

# No Gmail token/credentials yet is a routine, anticipated failure -- not a
# bug -- so run() maps it to exit 1 (expected_failure) instead of exit 3
# (a crash with a traceback the caller reads as "something broke").
EXPECTED_FAILURES = (GmailAuthError,)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(
        prog="moonlighter-email",
        description=__doc__,
        epilog=slice_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="classify recent replies and advance applications")
    register_parser = sub.add_parser(
        "register", help="mark a job applied and mint its tracking alias"
    )
    register_parser.add_argument("job_id", type=int)
    sub.add_parser("doctor", help="where the state lives and whether the config loads, as JSON")
    return parser.parse_args(argv)


async def _run(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if arguments.command == "doctor":
        return doctor_payload()
    config, _profile = bootstrap()
    if arguments.command == "register":
        result = register_application(arguments.job_id, config)
        return register_to_dict(result), (
            EXIT_OK if result.kind is RegisterKind.REGISTERED else EXIT_NOTHING
        )
    updates = await sync_responses(config, make_caller(config))
    return {"kind": "synced", "updates": updates}, (EXIT_OK if updates else EXIT_NOTHING)


def main() -> None:  # pragma: no cover - entry point (boundary)
    arguments = parse_args()
    sys.exit(run(lambda: _run(arguments), expected=EXPECTED_FAILURES))
