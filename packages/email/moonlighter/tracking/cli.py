"""moonlighter-email: read application replies from a shell.

    moonlighter-email sync
    moonlighter-email register JOB_ID [--status S] [--applied-at YYYY-MM-DD] [--notes TEXT]
                                      [--reply-mailbox-unswept | --reply-mailbox-swept]
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

`register JOB_ID` records an application made outside the tool and mints its
+ref tracking alias, using only moonlighter-core models -- so it works the
same in a standalone email install. --status (default submitted), --applied-at
and --notes describe it; --reply-mailbox-unswept marks one whose replies may
land in a mailbox the sync does not read (the 45-day no-response rule skips
it), --reply-mailbox-swept clears that. An existing application is never
overwritten: a draft is promoted, a missing date filled, a note appended.
Exit 0 (kind "registered") when the job exists, 1 (kind "job_not_found") when
it doesn't, 2 (kind "usage_error") on an unknown --status or a malformed date.
"""

import argparse
import sys
from datetime import date, datetime, time
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
from moonlighter.tracking.register import (
    ACCEPTED_STATUSES,
    RegisterKind,
    RegisterRequest,
    register_application,
    register_to_dict,
)
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
    register_parser.add_argument("--status", default="submitted", choices=ACCEPTED_STATUSES)
    register_parser.add_argument(
        "--applied-at", type=date.fromisoformat, default=None, help="YYYY-MM-DD"
    )
    register_parser.add_argument("--notes", default="", help="appended with today's date")
    mailbox = register_parser.add_mutually_exclusive_group()
    mailbox.add_argument(
        "--reply-mailbox-unswept",
        dest="reply_mailbox_unswept",
        action="store_const",
        const=True,
        default=None,
        help="replies may land in a mailbox the sync does not read",
    )
    mailbox.add_argument(
        "--reply-mailbox-swept",
        dest="reply_mailbox_unswept",
        action="store_const",
        const=False,
        help="clear --reply-mailbox-unswept",
    )
    sub.add_parser("doctor", help="where the state lives and whether the config loads, as JSON")
    return parser.parse_args(argv)


def _register_request(arguments: argparse.Namespace) -> RegisterRequest:
    given: date | None = arguments.applied_at
    return RegisterRequest(
        arguments.status,
        datetime.combine(given, time()) if given else None,
        arguments.notes,
        arguments.reply_mailbox_unswept,
    )


async def _run(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if arguments.command == "doctor":
        return doctor_payload()
    config, _profile = bootstrap()
    if arguments.command == "register":
        result = register_application(arguments.job_id, config, _register_request(arguments))
        return register_to_dict(result), (
            EXIT_OK if result.kind is RegisterKind.REGISTERED else EXIT_NOTHING
        )
    updates = await sync_responses(config, make_caller(config))
    return {"kind": "synced", "updates": updates}, (EXIT_OK if updates else EXIT_NOTHING)


def main() -> None:  # pragma: no cover - entry point (boundary)
    arguments = parse_args()
    sys.exit(run(lambda: _run(arguments), expected=EXPECTED_FAILURES))
