> **[Leia em Português](README.pt.md)**

# candidatador-de-vagas

AI-powered job application pipeline. Scans job boards, scores candidate fit via LLM, and automates browser-based applications — all driven from Claude through a [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server.

## How it works

1. **Scan** — fetches job listings from Greenhouse, Lever, Ashby, and LinkedIn for a company list you configure.
2. **Evaluate** — scores each job against your profile using an LLM; jobs below the threshold are archived automatically.
3. **Apply** — fills and submits application forms in a real browser (Playwright), using LLM-generated answers tailored to each posting.
4. **Track** — monitors your Gmail inbox for interview invitations and updates the pipeline status.

All steps are exposed as MCP tools and orchestrated by Claude in a conversation.

## Architecture

A [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) of 5 namespace packages (`candidatador.*`), feature-sliced:

| Package | Namespace | Purpose |
|---------|-----------|---------|
| `candidatador-core` | `candidatador.core` | DB (Peewee/SQLite), config, browser driver, LLM client |
| `candidatador-scan` | `candidatador.discovery` | ATS scrapers and LLM-based job scoring |
| `candidatador-apply` | `candidatador.application` | Form filler, answer generator, work-auth resolver |
| `candidatador-email` | `candidatador.tracking` | Gmail sync and interview stage classification |
| `candidatador-full` | `candidatador.server` | FastMCP server — wires all packages together |

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- Chrome, Chromium, or Brave (for browser automation)
- [Claude Code CLI](https://claude.ai/code) — or an `ANTHROPIC_API_KEY` for `llm_backend: api`
- Gmail OAuth credentials (optional — only for email tracking)

## Setup

### 1. Install

```bash
git clone https://github.com/albertosca/gauntler
cd candidatador-de-vagas
uv sync --all-packages
```

### 2. Configure

Copy the example files to your `CANDIDATADOR_HOME` (defaults to `~/.candidatador/`) and edit:

```bash
mkdir -p ~/.candidatador
cp config.example.yaml ~/.candidatador/config.yaml
cp profile.example.yaml ~/.candidatador/profile.yaml
cp company_list.example.yaml ~/.candidatador/company_list.yaml
```

Key fields in `config.yaml`:

| Field | Description |
|-------|-------------|
| `browser_path` | Path to your Chrome/Chromium/Brave executable |
| `llm_backend` | `"cli"` (Claude Code session) or `"api"` (Anthropic API key) |
| `score_threshold` | Jobs below this score (0–10) are archived |
| `work_authorization` | Your citizenship country and ATS answer strings |

Fill `profile.yaml` with your real experience, skills, and `criteria` (hard/soft filters drive scoring).

Edit `company_list.yaml` to add the companies and ATS platform you want to scan.

### 3. Gmail tracking (optional)

1. Create a project in [Google Cloud Console](https://console.cloud.google.com), enable the Gmail API, and download OAuth credentials as `client.json`.
2. Place the file at `~/.candidatador/gmail-client.json`.
3. The first call to `setup_email` opens a browser for authorization and saves the token.

### 4. Register as an MCP server

Add to `~/.claude/settings.json` (or your project `settings.json`):

```json
{
  "mcpServers": {
    "candidatador": {
      "command": "/path/to/candidatador-de-vagas/.venv/bin/python",
      "args": ["-m", "candidatador.server"]
    }
  }
}
```

Restart Claude Code — the tools below will appear automatically.

## MCP tools

| Tool | Description |
|------|-------------|
| `scan_and_evaluate` | Fetch and score jobs from all configured ATS sources |
| `list_jobs` | List jobs by status (`new`, `scored`, `applied`, `archived`, …) |
| `get_job` | Show full details and pipeline history for a job |
| `add_job` | Manually add a job by URL |
| `apply_jobs` | Batch-apply to a list of job IDs |
| `fill_application` | Fill a form and pause for review before submitting |
| `submit_application` | Submit an already-filled application |
| `confirm_apply` | Fill and submit in one atomic step |
| `retry_apply` | Retry a failed application |
| `login` | Open browser and persist session (LinkedIn) |
| `update_status` | Manually move a job through the pipeline |
| `setup_email` | Authorize Gmail OAuth |
| `sync_email_responses` | Pull latest replies and classify interview stages |
| `get_pipeline` | Full pipeline summary |

## License

AGPL-3.0 — see [LICENSE](LICENSE).  
See [DISCLAIMER.md](DISCLAIMER.md) for important notes on ToS, automation, and LLM backend usage.
