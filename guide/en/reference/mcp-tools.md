🇺🇸 [English](mcp-tools.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/reference/mcp-tools/)

# MCP tools

The `moonlighter` MCP server exposes 19 tools. You rarely call them by name: ask Claude in plain words ("scan my companies", "prepare the application for job 42") and it picks the tool. The names below are what shows up in Claude's tool calls.

## Scan and score

| Tool | Description |
|------|-------------|
| `scan_and_evaluate` | Fetch and score jobs from all configured ATS sources (`phase1` by default; ask for `all` to cover every phase). A posting already stored under another URL (same company, title and text) is archived as a duplicate with no LLM call. The scan ends with the no-response rule, below |
| `scan_company` | Scan one company's board right now and score the new postings, without editing `company_list.yaml` |
| `add_job` | Manually add a job by URL. `track=true` keeps a job you already chose to pursue as `reviewed`, whatever its score |
| `verify_job` | Score a job left as `needs_review` (empty description), from page text you copy off the posting |
| `archive_stale_jobs` | Archive jobs that disappeared from their source; a company whose check fails is reported and left untouched, and a job added by URL (no listing to check) is listed with its link for you to confirm |

## Browse the pipeline

| Tool | Description |
|------|-------------|
| `list_jobs` | List jobs by status (`new`, `needs_review`, `applied`, `rejected`, `archived`, …) |
| `get_job` | Show full details and pipeline history for a job |
| `get_pipeline` | Full pipeline summary, one section per status (`no_response` and `archived` included, so the sections add up to the total) — and setup problems, such as a missing profile or CV |
| `reopen_job` | Bring an archived job back to `reviewed`, to apply to it anyway |
| `update_status` | Move an application that already exists through the pipeline (`submitted`, `screening`, `interviews`, `offer`, `rejected`, `draft`, `no_response`) |
| `register_application` | Record an application you made outside the tool, in one step: creates it if missing, takes an archived job out of the archive, and never overwrites one that exists. Applied to job 42 by hand on Nov 10 → `register_application(42, applied_at="2026-11-10")` |

## Prepare applications

| Tool | Description |
|------|-------------|
| `prepare_application` | Compose every answer for a job's application form into one reviewable sheet, for you to paste in and submit yourself |
| `prepare_application_from_paste` | Same as `prepare_application`, for a form whose questions no API publishes — pass it the text you copied off the page |
| `list_answer_bank` | Every banked screening answer, most recently used first; expired ones marked |
| `forget_answer` | Delete one banked answer so the next application asks the LLM again |
| `bootstrap_cv_pool` | Draft a CV pool + template from your profile.yaml — a first draft to review |
| `skip_cv_bootstrap` | Decline the CV-pool bootstrap offer once, permanently |

## Track replies

| Tool | Description |
|------|-------------|
| `setup_email` | Authorize Gmail OAuth |
| `sync_email_responses` | Pull latest replies and classify interview stages |

## The no-response rule

At the end of every `scan_and_evaluate`, a `submitted` application with no sign of life (no status change, no dated note) for `no_response_after_days` (45 by default) becomes `no_response`, a status of its own, apart from `rejected`. Applications in `screening`, `interviews` or `offer` past that age are only listed, for you to decide.

The rule runs only when a complete email sync finished within `email_sync_max_age_days` (7 by default); otherwise the scan report says it did not run. A sync is complete when it classified every message in its window and stayed under its 500-message cap.

Each complete sync records the start of the window it read, `email.lookback_days` back. An application is marked only when an unbroken chain of those windows reaches back to its last sign of life; the others are listed as waiting: raise `email.lookback_days` in the config and run `sync_email_responses`.

An application whose replies may land in a mailbox the sync does not read is left alone: pass `reply_mailbox_unswept=true` to `register_application`.

Guides for the flows behind these tools: [First scan](../getting-started/first-scan.md), [Answer bank](../guides/answer-bank.md), [Tailored CV](../guides/tailored-cv.md), [Gmail tracking](../getting-started/gmail.md).

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
