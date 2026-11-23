"""Builds the SyncUpdate list a faked sync_responses returns, from the dicts the CLI emits."""

from collections.abc import Mapping, Sequence
from typing import Any

from moonlighter.tracking.sync.report import SyncUpdate

_DEFAULTS: dict[str, Any] = {
    "job_id": None,
    "status_advanced": False,
    "company": None,
    "title": None,
    "stage": None,
    "match_type": "ref",
    "summary": "",
}


def as_sync_updates(entries: Sequence[Mapping[str, Any]]) -> list[SyncUpdate]:
    """Each entry in the CLI's JSON shape ("type", optional keys left out) as a SyncUpdate."""
    updates = []
    for entry in entries:
        fields = {**_DEFAULTS, **entry}
        fields["message_type"] = fields.pop("type")
        updates.append(SyncUpdate(**fields))
    return updates
