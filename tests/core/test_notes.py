"""Dated notes: appending one, and reading the newest date back."""

from datetime import date

from moonlighter.core.notes import append_dated_note, latest_note_date


def test_append_to_empty_notes():
    assert (
        append_dated_note(None, "applied by hand", date(2026, 11, 17))
        == "[2026-11-17] applied by hand"
    )


def test_append_keeps_existing_notes():
    notes = append_dated_note("[2026-10-01] first", "second", date(2026, 11, 17))
    assert notes == "[2026-10-01] first\n[2026-11-17] second"


def test_latest_date_is_the_newest_line_start_date():
    notes = "[2026-10-01] a\n[2026-11-03] b\n[2026-10-20] c"
    assert latest_note_date(notes) == date(2026, 11, 3)


def test_malformed_and_mid_line_dates_are_ignored():
    notes = "[2026-13-45] bad month\nreply on [2026-11-10] mid-line\n[2026-09-01] good"
    assert latest_note_date(notes) == date(2026, 9, 1)


def test_no_dated_note_is_none():
    assert latest_note_date(None) is None
    assert latest_note_date("") is None
    assert latest_note_date("free text without a date") is None
