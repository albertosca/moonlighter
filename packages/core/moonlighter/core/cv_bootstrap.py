"""Whether the one-time CV-pool bootstrap offer was declined, and recording that it was."""

from moonlighter.core.db import CVBootstrapDecline


def cv_bootstrap_declined() -> bool:
    return CVBootstrapDecline.select().exists()


def record_cv_bootstrap_decline() -> None:
    if not cv_bootstrap_declined():
        CVBootstrapDecline.create()
