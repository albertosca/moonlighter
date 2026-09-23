🇺🇸 [English](mcp-tools.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/reference/mcp-tools/)

# MCP tools

The `moonlighter` MCP server exposes 17 tools. You rarely call them by name: ask Claude in plain words ("scan my companies", "prepare the application for job 42") and it picks the tool. The names below are what shows up in Claude's tool calls.

## Scan and score

| Tool | Description |
|------|-------------|
| `scan_and_evaluate` | Fetch and score jobs from all configured ATS sources (`phase1` by default; ask for `all` to cover every phase) |
| `scan_company` | Scan one company's board right now and score the new postings, without editing `company_list.yaml` |
| `add_job` | Manually add a job by URL |
| `verify_job` | Score a job left as `needs_review` (empty description), from page text you copy off the posting |
| `archive_stale_jobs` | Archive jobs that disappeared from their source; a company whose check fails is reported and left untouched |

## Browse the pipeline

| Tool | Description |
|------|-------------|
| `list_jobs` | List jobs by status (`new`, `needs_review`, `applied`, `rejected`, `archived`, …) |
| `get_job` | Show full details and pipeline history for a job |
| `get_pipeline` | Full pipeline summary — and setup problems, such as a missing profile or CV |
| `update_status` | Manually move a job's application through the pipeline (`submitted`, `screening`, `interviews`, `offer`, `rejected`, `draft`) |

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

Guides for the flows behind these tools: [First scan](../getting-started/first-scan.md), [Answer bank](../guides/answer-bank.md), [Tailored CV](../guides/tailored-cv.md), [Gmail tracking](../getting-started/gmail.md).

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
