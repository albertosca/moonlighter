"""Record a sync as a complete sweep, the only kind the no-response rule may trust."""

import logging
from datetime import datetime, timedelta

from moonlighter.core.db import EmailSyncRun
from moonlighter.tracking.gmail.messages import MAXIMUM_MESSAGES_PER_SYNC

logger = logging.getLogger(__name__)


def record_sweep_if_complete(
    started: datetime, *, lookback_days: int, fetched: int, skipped: int
) -> None:
    """Write EmailSyncRun only when every message in the window was read and classified.

    A message left unclassified may be the reply that keeps an application alive, and a
    fetch that filled the cap may have left older messages of the window unfetched
    (a window of exactly the cap counts as cut: the two cannot be told apart).
    """
    if skipped or fetched >= MAXIMUM_MESSAGES_PER_SYNC:
        logger.warning(
            "sync_responses: %d message(s) left unclassified, %d fetched (cap %d) — "
            "not recorded as a complete sweep; the no-response rule waits for one",
            skipped,
            fetched,
            MAXIMUM_MESSAGES_PER_SYNC,
        )
        return
    EmailSyncRun.create(window_start=started - timedelta(days=lookback_days))
