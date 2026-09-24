🇺🇸 [English](install.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/getting-started/install/)

# Install moonlighter

moonlighter runs on your own machine as an MCP server for Claude Code (or any MCP client), plus one command-line tool per package. Setup is three steps: run the wizard, fill in two YAML files, register the server.

## Requirements

- [uv](https://docs.astral.sh/uv/) — fetches Python 3.14 for you; no separate install needed
- Chrome, Chromium, or Brave — optional, only needed if you install a browser-based scan extension (e.g. LinkedIn scanning, see [Extensions](../guides/extensions.md)). The base product (scanning the configured ATS APIs and preparing applications) never opens a browser.
- An LLM backend, switchable in `config.yaml` at any time:
  - `llm_backend: cli` (default) — the [Claude Code CLI](https://claude.ai/code), billed to your Claude subscription. No API key.
  - `llm_backend: api` — the Anthropic SDK, billed to API credits. Requires `ANTHROPIC_API_KEY`: from the environment, or, when it is not set there, from a line `ANTHROPIC_API_KEY=...` in `~/.config/anthropic/api.env`.
- Gmail OAuth credentials (optional — only for [Gmail tracking](gmail.md))

## Setup

In a hurry? The whole thing is:

```bash
uvx moonlighter init                  # wizard: writes config.yaml
# fill in profile.yaml and company_list.yaml (examples below)
claude mcp add-json --scope user moonlighter '{"command":"uvx","args":["moonlighter"]}'
# new Claude session → "scan my companies"
```

The details:

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

Then register the MCP server:

```bash
claude mcp add-json --scope user moonlighter '{"command":"uvx","args":["moonlighter"]}'
```

Using a different MCP client? Register the same command and args (`uvx` / `["moonlighter"]`) with your client's own registration mechanism — the `claude mcp add-json` command above is specific to the Claude Code CLI.

### After either option

The wizard writes `config.yaml` into `MOONLIGHTER_HOME` (defaults to `~/.moonlighter/`). Two files still need your input:

| File | What goes in it |
|------|-----------------|
| `profile.yaml` | Your experience, skills, and `criteria` (the hard and soft filters that drive scoring) |
| `company_list.yaml` | The companies to scan and which ATS each one uses |

Start from [`profile.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/profile.example.yaml) and [`company_list.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/company_list.example.yaml).

The wizard writes a minimal `config.yaml`; [`config.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/config.example.yaml) documents the rest of the configuration surface (summarised in [Configuration](../reference/config.md)), notably the `cv` block and the `email` block. The `cv` block is only needed to use a different resume per company: by default `prepare_application` points you at `cv.pdf` from `MOONLIGHTER_HOME` for the form's file-upload question, and tells you plainly if none is configured. `profile.yaml`, `company_list.yaml`, `config.yaml`, and `cv.pdf` (your resume — moonlighter names it for you to attach, never uploads it itself) all belong in `MOONLIGHTER_HOME` (defaults to `~/.moonlighter/`).

Restart Claude Code, or start a new session, before the moonlighter tools appear. Once connected, ask Claude to run `get_pipeline` — besides the application funnel, it reports setup problems such as a missing profile, CV, or browser.

Next: [run your first scan](first-scan.md). Reply tracking is optional and set up separately — see [Gmail tracking](gmail.md).

## Developing on moonlighter

To work on the code rather than just use it, see [CONTRIBUTING.md](https://github.com/albertosca/moonlighter/blob/main/CONTRIBUTING.md).

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
