"""The `prepare` subcommand: ingest a posting when given a URL, then compose its sheet."""

import argparse
import sys
from pathlib import Path
from typing import Any

from moonlighter.application.assisted.service import (
    prepare_application,
    prepare_application_from_paste,
)
from moonlighter.application.assisted.sheet.results import (
    SheetKind,
    failed_sheet,
    sheet_result_to_dict,
)
from moonlighter.core.cli import EXIT_NOTHING, EXIT_OK
from moonlighter.core.web.ingest import job_from_url


def _read_paste(source: str) -> str:
    return sys.stdin.read() if source == "-" else Path(source).read_text()


async def run_prepare(
    arguments: argparse.Namespace, config: dict[str, Any], profile: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Prepare the sheet for --url's posting or JOB_ID; exit 0 only when a sheet came out."""
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
            job_id, _read_paste(arguments.paste), config, profile=profile
        )
    else:
        result = await prepare_application(job_id, config, profile)
    code = EXIT_OK if result.kind is SheetKind.SHEET else EXIT_NOTHING
    return sheet_result_to_dict(result), code
