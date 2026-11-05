"""format_archive_result words each archive outcome."""

from moonlighter.discovery.archive import ArchiveResult, format_archive_result


def testformat_archive_result_empty():
    assert format_archive_result(ArchiveResult()) == "No closed jobs found."


def testformat_archive_result_archived_only():
    result = ArchiveResult(
        archived=[{"company": "acme", "title": "Engineer", "url": "https://x.com/1"}]
    )
    formatted = format_archive_result(result)
    assert "1 job(s) archived" in formatted
    assert "acme / Engineer — https://x.com/1" in formatted


def testformat_archive_result_failed_only():
    result = ArchiveResult(failed_companies=["acme"])
    formatted = format_archive_result(result)
    assert "No closed jobs found." in formatted
    assert "Could not check: acme" in formatted


def testformat_archive_result_archived_and_failed():
    result = ArchiveResult(
        archived=[{"company": "acme", "title": "Engineer", "url": "https://x.com/1"}],
        failed_companies=["beta"],
    )
    formatted = format_archive_result(result)
    assert "1 job(s) archived" in formatted
    assert "Could not check: beta" in formatted


def test_format_archive_result_lists_jobs_to_confirm_by_hand():
    result = ArchiveResult(
        to_confirm=[
            {
                "id": 42,
                "score": 7.5,
                "status": "reviewed",
                "age_days": 12,
                "company": "Flywheel",
                "title": "Backend Engineer",
                "url": "https://hiring.example/jobs/7",
            },
            {
                "id": 43,
                "score": None,
                "status": "needs_review",
                "age_days": None,
                "company": "Acme",
                "title": "Engineer",
                "url": "https://acme.example/1",
            },
        ]
    )
    formatted = format_archive_result(result)
    assert "No closed jobs found." in formatted
    assert "2 job(s) have no listing to check against" in formatted
    assert "#42 | 7.5 | reviewed | 12d | Flywheel — Backend Engineer" in formatted
    assert "https://hiring.example/jobs/7" in formatted
    assert "#43 | — | needs_review | ?d | Acme — Engineer" in formatted


def test_format_archive_result_orders_its_sections_with_blank_lines_between_them():
    result = ArchiveResult(
        archived=[{"company": "acme", "title": "Engineer", "url": "https://x.com/1"}],
        aged=[{"company": "globex", "title": "Designer", "url": "https://x.com/2"}],
        max_age_days=30,
        to_confirm=[
            {
                "id": 42,
                "score": 8,
                "status": "reviewed",
                "age_days": 12,
                "company": "Flywheel",
                "title": "Backend Engineer",
                "url": "https://hiring.example/jobs/7",
            }
        ],
        failed_companies=["beta", "gamma"],
    )
    assert format_archive_result(result) == (
        "1 job(s) archived (closed at source):\n"
        "  - acme / Engineer — https://x.com/1\n"
        "1 portal job(s) archived by age "
        "(older than 30 days; a portal feed cannot be re-checked):\n"
        "  - globex / Designer — https://x.com/2\n"
        "\n"
        "1 job(s) have no listing to check against — open each link and say which are closed:\n"
        "  #42 | 8.0 | reviewed | 12d | Flywheel — Backend Engineer\n"
        "    https://hiring.example/jobs/7\n"
        "\n"
        "⚠️  Could not check: beta, gamma"
    )


def test_format_archive_result_with_only_aged_jobs_still_opens_with_no_closed_jobs():
    result = ArchiveResult(
        aged=[{"company": "globex", "title": "Designer", "url": "https://x.com/2"}],
        max_age_days=14,
    )
    assert format_archive_result(result) == (
        "No closed jobs found.\n"
        "1 portal job(s) archived by age "
        "(older than 14 days; a portal feed cannot be re-checked):\n"
        "  - globex / Designer — https://x.com/2"
    )
