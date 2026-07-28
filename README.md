> **[Leia em Português](README.pt.md)**

# moonlighter

AI-powered job application pipeline. Scans job boards, scores candidate fit via LLM, and automates browser-based applications — all driven from Claude through a [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server.

## How it works

1. **Scan** — fetches job listings from Greenhouse, Lever, Ashby, Recruitee, Workable, and SmartRecruiters for a company list you configure, plus optional remote-first boards (RemoteOK, Remotive, WeWorkRemotely, HN Who's Hiring) and Gupy, both config-gated off by default. LinkedIn scanning/Easy Apply is available as a separate, privately-distributed extension — see [Extensions (adding a new ATS)](#extensions-adding-a-new-ats) below.
2. **Evaluate** — scores each job against your profile using an LLM; jobs below the threshold are archived automatically.
3. **Apply** — fills and submits application forms in a real browser (Playwright), using LLM-generated answers tailored to each posting.
4. **Track** — monitors your Gmail inbox for interview invitations and updates the pipeline status.

All steps are exposed as MCP tools and orchestrated by Claude in a conversation.

## Architecture

A [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) of 5 namespace packages (`moonlighter.*`), feature-sliced:

| Package | Namespace | Purpose |
|---------|-----------|---------|
| `moonlighter-core` | `moonlighter.core` | DB (Peewee/SQLite), config, browser driver, LLM client |
| `moonlighter-scan` | `moonlighter.discovery` | ATS scrapers and LLM-based job scoring |
| `moonlighter-apply` | `moonlighter.application` | Form filler, answer generator, work-auth resolver |
| `moonlighter-email` | `moonlighter.tracking` | Gmail sync and interview stage classification |
| `moonlighter` | `moonlighter.server` | FastMCP server — wires all packages together |

## Requirements

- [uv](https://docs.astral.sh/uv/) — fetches Python 3.14 for you; no separate install needed
- Chrome, Chromium, or Brave (moonlighter drives a real browser so your logged-in sessions work)
- [Claude Code CLI](https://claude.ai/code) — or an `ANTHROPIC_API_KEY` for `llm_backend: api`
- Gmail OAuth credentials (optional — only for email tracking)

## Setup

### Option A — Claude Code plugin (recommended)

```
/plugin marketplace add albertosca/moonlighter
/plugin install moonlighter@moonlighter
```

The first command registers the marketplace; the second installs the plugin from it.

Then run the setup wizard:

```bash
uvx moonlighter init
```

### Option B — any MCP client

```bash
uvx moonlighter init
```

Then add to `~/.claude/settings.json` (or your client's equivalent):

```json
{
  "mcpServers": {
    "moonlighter": {
      "command": "uvx",
      "args": ["moonlighter"]
    }
  }
}
```

The wizard writes `config.yaml` into `MOONLIGHTER_HOME` (defaults to `~/.moonlighter/`). Two
files still need your input:

| File | What goes in it |
|------|-----------------|
| `profile.yaml` | Your experience, skills, and `criteria` (the hard and soft filters that drive scoring) |
| `company_list.yaml` | The companies to scan and which ATS each one uses |

Start from [`profile.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/profile.example.yaml) and [`company_list.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/company_list.example.yaml).

### Gmail tracking (optional)

1. Create a project in [Google Cloud Console](https://console.cloud.google.com), enable the
   Gmail API, and download OAuth credentials as `client.json`.
2. Place the file at `~/.moonlighter/gmail-client.json`.
3. The first call to `setup_email` opens a browser for authorization and saves the token.

### Developing on moonlighter

To work on the code rather than just use it, see [CONTRIBUTING.md](CONTRIBUTING.md).

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
| `login` | Open browser and persist session for a platform that needs one (only available if an extension registers it — see below) |
| `update_status` | Manually move a job through the pipeline |
| `setup_email` | Authorize Gmail OAuth |
| `sync_email_responses` | Pull latest replies and classify interview stages |
| `get_pipeline` | Full pipeline summary |

## Extensions (adding a new ATS)

Every ATS integration you see above (Greenhouse, Lever, Ashby, Recruitee, Workable, SmartRecruiters, Gupy)
is a normal part of this repo — but moonlighter also supports **extensions**: separate, independently
installed Python packages that register a new scanner or applier without forking or modifying this repo
at all. This is how LinkedIn support is distributed — not because the mechanism is LinkedIn-specific, but
because LinkedIn's own Terms of Service explicitly and unambiguously prohibit automation (see
[DISCLAIMER.md](DISCLAIMER.md)), so that one integration ships as an opt-in extension instead of bundled
code anyone who clones this repo gets by default.

### How it works

An extension is a normal Python package that:

1. Depends on the `moonlighter-*` packages it needs (typically `moonlighter-core` plus whichever of
   `moonlighter-scan`/`moonlighter-apply` it extends), pinned to a released tag of this repo.
2. Ships its own module(s) implementing a `BaseScanner` subclass (see
   `packages/scan/moonlighter/discovery/sources/base.py`) and/or a `BaseApplier` subclass (see
   `packages/apply/moonlighter/application/appliers/base.py`).
3. Declares itself via `entry_points` in its own `pyproject.toml` — no code in this repo ever imports or
   names the extension:

```toml
[project.entry-points."moonlighter.scanners"]
my_platform = "my_package.my_module:MyScanner"

[project.entry-points."moonlighter.appliers"]
my_platform = "my_package.my_module:MyApplier"

# Optional: a platform your applier needs a saved browser login for (the `login` MCP tool)
[project.entry-points."moonlighter.login_urls"]
my_platform = "my_package.my_module:MY_PLATFORM_LOGIN_URL"

# Optional: a browser-based staleness check for a source with no listing API
[project.entry-points."moonlighter.staleness_checkers"]
my_platform = "my_package.my_module:check_staleness"
```

4. Gets installed into the **same** Python environment moonlighter runs from (`uv add --editable`/
   `pip install` your extension package alongside moonlighter's own dependencies). At runtime,
   `moonlighter.core.plugins.discover_entry_points`/`discover_entry_points_by_name` enumerate whatever's
   registered under each group — an environment with no extensions installed behaves identically to today
   (empty list/dict, nothing breaks).

Because the top-level `moonlighter` package is a [PEP 420 namespace package](https://peps.python.org/pep-0420/)
(no `__init__.py` at that level), an extension can even contribute its own top-level subpackage (e.g.
`moonlighter/my_extension/`) that coexists with `moonlighter.core`/`moonlighter.discovery`/etc. — just don't
place files *inside* an existing subpackage like `moonlighter/discovery/sources/` or
`moonlighter/application/appliers/`, since those are regular (non-namespace) packages owned entirely by
this repo's own distributions, and a second distribution writing to the same path silently collides at
install time. Give your extension its own top-level directory instead.

### Real example

The private `moonlighter-linkedin` extension (not published, for the reason above) follows exactly this
pattern — its `LinkedInScanner`/`LinkedInApplier` live in their own `moonlighter/linkedin_ext/` package,
registered via all four entry_points groups above. If you're building your own extension, that's the
reference shape to copy.

## License

AGPL-3.0 — see [LICENSE](LICENSE).  
See [DISCLAIMER.md](DISCLAIMER.md) for important notes on ToS, automation, and LLM backend usage.
See [PRIVACY.md](PRIVACY.md) for what data this tool stores and where it goes.
