"""How the rule's outcome reads in the scan report."""

from moonlighter.discovery.unanswered import UnansweredResult, format_unanswered_result

LAST_SYNC = "2026-11-16T10:00:00"


def test_not_run_names_the_last_sync():
    text = format_unanswered_result(UnansweredResult(ran=False, last_sync="2026-11-09T10:00:00"))
    assert text == (
        "No-response rule did not run: the last complete email sync was 2026-11-09T10:00:00, "
        "older than email_sync_max_age_days. Run sync_email_responses first."
    )


def test_not_run_without_any_sync():
    text = format_unanswered_result(UnansweredResult(ran=False, last_sync=None))
    assert text == (
        "No-response rule did not run: there is no complete email sync yet. "
        "Run sync_email_responses first."
    )


def test_lists_marked_review_and_held():
    text = format_unanswered_result(
        UnansweredResult(
            ran=True,
            last_sync=LAST_SYNC,
            marked=[{"job_id": 1, "company": "A", "title": "Eng", "days": 50}],
            to_review=[
                {"job_id": 2, "company": "B", "title": "Eng", "days": 60, "status": "screening"}
            ],
            held=[{"job_id": 3, "company": "C", "title": "Eng", "days": 70}],
            after_days=45,
        )
    )
    assert text == (
        "1 application(s) marked no_response (no sign of life for 45+ days):\n"
        "  #1 A/Eng (50 days)\n"
        "\n"
        "1 application(s) past the age in a later stage:\n"
        "  #2 B/Eng — screening, 60 days without news: decide by hand\n"
        "\n"
        "1 application(s) left alone:\n"
        "  #3 C/Eng (70 days) — held: replies may be in a mailbox the sync does not read"
    )


def test_only_one_block_has_no_stray_blank_lines():
    text = format_unanswered_result(
        UnansweredResult(
            ran=True,
            last_sync=LAST_SYNC,
            held=[{"job_id": 3, "company": "C", "title": "Eng", "days": 70}],
        )
    )
    assert not text.startswith("\n")
    assert not text.endswith("\n")


def test_nothing_to_report_is_empty():
    assert format_unanswered_result(UnansweredResult(ran=True, last_sync=LAST_SYNC)) == ""
