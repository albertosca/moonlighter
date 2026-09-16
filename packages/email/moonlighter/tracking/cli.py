"""moonlighter-email: read application replies from a shell.

    moonlighter-email sync
    moonlighter-email register JOB_ID

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
from typing import Any

from moonlighter.core.cli import EXIT_NOTHING, EXIT_OK, JsonArgumentParser, bootstrap, run
from moonlighter.core.llm import make_caller
from moonlighter.tracking.email_monitor import sync_responses
from moonlighter.tracking.gmail_client import GmailAuthError
from moonlighter.tracking.register import RegisterKind, register_application, register_to_dict

# No Gmail token/credentials yet is a routine, anticipated failure -- not a
# bug -- so run() maps it to exit 1 (expected_failure) instead of exit 3
# (a crash with a traceback the caller reads as "something broke").
EXPECTED_FAILURES = (GmailAuthError,)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(
        prog="moonlighter-email",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="classify recent replies and advance applications")
    register_parser = sub.add_parser(
        "register", help="mark a job applied and mint its tracking alias"
    )
    register_parser.add_argument("job_id", type=int)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    config, _profile = bootstrap()
    if args.command == "register":
        r = register_application(args.job_id, config)
        return register_to_dict(r), (EXIT_OK if r.kind is RegisterKind.REGISTERED else EXIT_NOTHING)
    updates = await sync_responses(config, make_caller(config))
    return {"kind": "synced", "updates": updates}, (EXIT_OK if updates else EXIT_NOTHING)


def main() -> None:  # pragma: no cover - entry point (boundary)
    import sys

    args = parse_args()
    sys.exit(run(lambda: _run(args), expected=EXPECTED_FAILURES))
