"""Pins how build_blocklist turns the model's answer into pattern lines, and what each kind of failure prints."""

from tests.scripts.build_blocklist.harness import after_header, proposal, run_main, scored

HEADER = "Jobs to analyze: {titles} across {companies} company/ies  [threshold=3.0]\n\n"


def test_only_safe_dict_entries_with_a_pattern_become_lines(monkeypatch, home, capsys):
    scored("Acme", "Recruiter Lead", 1.0)
    answer = [
        proposal("Recruiter ", reasoning="r1"),
        proposal("unsafe", safe=False),
        proposal(""),
        "not a dict",
        proposal("string-safe", safe="true"),
        {"pattern": "no reason", "safe": True},
    ]

    run_main(monkeypatch, "--dry-run", answers={"Acme": answer})

    assert after_header(capsys.readouterr().out) == (
        HEADER.format(titles=1, companies=1)
        + "▶ Acme (1 jobs)...\n"
        + f"  + {'recruiter'!r:40s} [DRY RUN]\n"
        "    → r1\n"
        f"  + {'no reason'!r:40s} [DRY RUN]\n"
        "    → \n"
        "\n"
        "No new patterns.\n"
    )


def test_an_answer_that_is_not_a_list_proposes_nothing(monkeypatch, home, capsys):
    scored("Acme", "Recruiter Lead", 1.0)

    run_main(monkeypatch, "--dry-run", answers={"Acme": proposal("recruiter")})

    assert after_header(capsys.readouterr().out) == (
        HEADER.format(titles=1, companies=1) + "▶ Acme (1 jobs)...\n"
        "  (no safe pattern identified)\n"
        "No new patterns.\n"
    )


def test_an_answer_that_cannot_be_parsed_is_reported_and_the_run_goes_on(monkeypatch, home, capsys):
    scored("Acme", "A", 1.0)
    scored("Beta", "B", 1.0)

    run_main(
        monkeypatch,
        "--dry-run",
        answers={"Acme": "no json here", "Beta": [proposal("beta-only", reasoning="ok")]},
    )

    output = after_header(capsys.readouterr().out)
    assert output.startswith(
        HEADER.format(titles=2, companies=2) + "▶ Acme (1 jobs)...\n  ⚠️  Error processing Acme: "
    )
    assert "  (no safe pattern identified)\n▶ Beta (1 jobs)...\n" in output
    assert f"  + {'beta-only'!r:40s} [DRY RUN]\n    → ok\n" in output


def test_a_failing_caller_is_reported_like_a_parse_error(monkeypatch, home, capsys):
    scored("Acme", "A", 1.0)

    run_main(monkeypatch, "--dry-run", answers={"Acme": RuntimeError("connection reset")})

    assert after_header(capsys.readouterr().out) == (
        HEADER.format(titles=1, companies=1) + "▶ Acme (1 jobs)...\n"
        "  ⚠️  Error processing Acme: connection reset\n"
        "  (no safe pattern identified)\n"
        "No new patterns.\n"
    )


def test_a_quota_error_stops_the_run_and_later_companies_are_never_asked(monkeypatch, home, capsys):
    scored("Acme", "A1", 1.0)
    scored("Acme", "A2", 1.0)
    scored("Beta", "B", 1.0)

    caller = run_main(
        monkeypatch, "--dry-run", answers={"Acme": RuntimeError("Rate Limit hit, retry later")}
    )

    assert [company for company, _, _ in caller.calls] == ["Acme"]
    assert after_header(capsys.readouterr().out) == (
        HEADER.format(titles=3, companies=2) + "▶ Acme (2 jobs)...\n"
        "🚫 SPEND LIMIT reached — stopping. Error: Rate Limit hit, retry later\n"
        "No new patterns.\n"
    )


def test_an_error_while_building_the_prompt_is_reported_and_the_run_goes_on(
    monkeypatch, home, capsys
):
    scored("Acme", "A", 1.0)
    scored("Beta", "B", 1.0)

    caller = run_main(monkeypatch, "--dry-run", profile={"top_skills": [1]})

    assert caller.calls == []
    assert after_header(capsys.readouterr().out) == (
        HEADER.format(titles=2, companies=2) + "▶ Acme (1 jobs)...\n"
        "  ✗ Error: sequence item 0: expected str instance, int found\n"
        "▶ Beta (1 jobs)...\n"
        "  ✗ Error: sequence item 0: expected str instance, int found\n"
        "No new patterns.\n"
    )


def test_a_bare_unfenced_list_loses_its_brackets_and_proposes_nothing(monkeypatch, home, capsys):
    scored("Acme", "A", 1.0)
    raw = '[{"pattern": "recruiter", "safe": true}]'

    run_main(monkeypatch, "--dry-run", answers={"Acme": raw})

    assert after_header(capsys.readouterr().out) == (
        HEADER.format(titles=1, companies=1) + "▶ Acme (1 jobs)...\n"
        "  (no safe pattern identified)\n"
        "No new patterns.\n"
    )
