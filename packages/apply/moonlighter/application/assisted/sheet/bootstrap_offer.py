"""The one-time offer to draft a tailored-CV pool, shown in place of a sheet until it is settled."""

from typing import Any

from moonlighter.application.assisted.sheet.results import SheetKind, SheetResult, failed_sheet
from moonlighter.application.cvgen.paths import resolved_pool_path
from moonlighter.core.cv_bootstrap import cv_bootstrap_declined

_CV_BOOTSTRAP_OFFER_MESSAGE = (
    "You don't have a tailored-CV pool yet. I can draft one from your profile.yaml — "
    "call the bootstrap_cv_pool tool to generate it, or skip_cv_bootstrap if you'd "
    "rather not use this feature. I'll keep offering this on every "
    "prepare_application until you either bootstrap a pool or skip it. "
    "From a shell: `moonlighter-apply bootstrap-cv` (add --skip to decline)."
)


def cv_bootstrap_offer(config: dict[str, Any]) -> SheetResult | None:
    """The sheet that offers to bootstrap a CV pool, or None once a pool exists or the offer was declined."""
    if resolved_pool_path(config).exists() or cv_bootstrap_declined():
        return None
    return failed_sheet(SheetKind.CV_BOOTSTRAP_OFFER, _CV_BOOTSTRAP_OFFER_MESSAGE)
