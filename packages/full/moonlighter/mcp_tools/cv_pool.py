"""MCP tools for the CV bullet pool: draft one from the profile, or decline the offer."""

from typing import Any

from mcp.server.mcpserver import Context

from moonlighter._tool_logging import tool_logged
from moonlighter.app_context import AppContext, refreshed_app_context
from moonlighter.application.cvgen.bootstrap import bootstrap_cv_pool as bootstrap_cv_pool_service
from moonlighter.application.cvgen.bootstrap_error import BootstrapError
from moonlighter.application.cvgen.compile import latex_available
from moonlighter.core.db import record_cv_bootstrap_decline
from moonlighter.core.llm.dispatch import make_caller


@tool_logged
async def bootstrap_cv_pool(*, context: Context[AppContext, Any]) -> str:
    """
    Draft a CV bullet pool + adapted template from your profile.yaml — a
    first draft you review and edit, not a finished document. Offered by
    prepare_application whenever it finds no pool yet (see its
    cv_bootstrap_offer response), until you bootstrap one or skip it.
    """  # noqa: D205, D212 - served verbatim as the MCP tool description
    app_context = refreshed_app_context(context)
    caller = make_caller(app_context.config)
    try:
        outcome = await bootstrap_cv_pool_service(app_context.profile, app_context.config, caller)
    except BootstrapError as error:
        return f"Could not draft a CV pool: {error}"
    # Two different reasons for a missing PDF, and naming the wrong one sends
    # the operator to install a pdflatex they already have. latex_available()
    # is the only thing that tells them apart.
    if outcome.pdf_path is not None:
        pdf_note = f" A draft PDF was compiled at {outcome.pdf_path}."
    elif latex_available():
        pdf_note = (
            " pdflatex is installed but the draft did not compile — "
            f"see the .log next to {outcome.template_path}."
        )
    else:
        pdf_note = (
            " pdflatex is not installed, so no PDF was compiled — "
            "the .tex is ready to compile yourself."
        )
    return (
        f"Drafted {outcome.bullet_count} bullets into {outcome.pool_path} "
        f"and adapted the template at {outcome.template_path}.{pdf_note} "
        "Please review it before your first real application uses it."
    )


@tool_logged
async def skip_cv_bootstrap() -> str:
    """
    Decline the CV-pool bootstrap offer. You won't be asked again — you can
    still call bootstrap_cv_pool yourself at any time later.
    """  # noqa: D205, D212 - served verbatim as the MCP tool description
    record_cv_bootstrap_decline()
    return "Understood — I won't offer to draft a CV pool again for this installation."
