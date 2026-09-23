🇺🇸 [English](mcp-tools.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/reference/mcp-tools/)

# MCP tools

## MCP tools

| Tool | Description |
|------|-------------|
| `scan_and_evaluate` | Fetch and score jobs from all configured ATS sources |
| `list_jobs` | List jobs by status (`new`, `scored`, `applied`, `archived`, …) |
| `get_job` | Show full details and pipeline history for a job |
| `add_job` | Manually add a job by URL |
| `prepare_application` | Compose every answer for a job's application form into one reviewable sheet, for you to paste in and submit yourself |
| `prepare_application_from_paste` | Same as `prepare_application`, for a form whose questions no API publishes — pass it the text you copied off the page |
| `update_status` | Manually move a job through the pipeline |
| `list_answer_bank` | Every banked screening answer, most recently used first; expired ones marked |
| `forget_answer` | Delete one banked answer so the next application asks the LLM again |
| `setup_email` | Authorize Gmail OAuth |
| `sync_email_responses` | Pull latest replies and classify interview stages |
| `get_pipeline` | Full pipeline summary |
| `bootstrap_cv_pool` | Draft a CV pool + template from your profile.yaml — a first draft to review |
| `skip_cv_bootstrap` | Decline the CV-pool bootstrap offer once, permanently |

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
