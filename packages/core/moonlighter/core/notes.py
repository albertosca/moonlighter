"""Notes stamped with the local day, one per line: `[YYYY-MM-DD] text`."""

import re
from datetime import date

_LINE_DATE = re.compile(r"^\[(\d{4}-\d{2}-\d{2})\]", re.MULTILINE)


def append_dated_note(existing: str | None, note: str, day: date) -> str:
    """The notes with one more line, stamped with `day`."""
    line = f"[{day.isoformat()}] {note}"
    return f"{existing}\n{line}" if existing else line


def latest_note_date(notes: str | None) -> date | None:
    """The newest valid date that starts a line; malformed and mid-line dates are ignored."""
    found: list[date] = []
    for text in _LINE_DATE.findall(notes or ""):
        try:
            found.append(date.fromisoformat(text))
        except ValueError:
            continue
    return max(found, default=None)
