"""The `bootstrap-cv` subcommand: draft a CV pool and template from profile.yaml, or decline."""

import argparse
from typing import Any

from moonlighter.application.cvgen.bootstrap import bootstrap_cv_pool
from moonlighter.core.cli import EXIT_OK
from moonlighter.core.db import record_cv_bootstrap_decline
from moonlighter.core.llm.dispatch import make_caller


async def run_bootstrap_cv(
    arguments: argparse.Namespace, config: dict[str, Any], profile: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Draft the pool, or with --skip record the decline without any LLM call."""
    if arguments.skip:
        record_cv_bootstrap_decline()
        return {"kind": "cv_bootstrap_skipped"}, EXIT_OK
    outcome = await bootstrap_cv_pool(profile, config, make_caller(config), force=arguments.force)
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
