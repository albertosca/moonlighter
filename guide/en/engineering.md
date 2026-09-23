🇺🇸 [English](engineering.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/engineering/)

# Engineering

## Architecture

A [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) of 5 namespace packages (`moonlighter.*`), feature-sliced:

| Package | Namespace | Purpose |
|---------|-----------|---------|
| `moonlighter-core` | `moonlighter.core` | DB (Peewee/SQLite), config, optional browser driver (`[browser]` extra), LLM client |
| `moonlighter-scan` | `moonlighter.discovery` | ATS scrapers and LLM-based job scoring |
| `moonlighter-apply` | `moonlighter.application` | Answer composer (curated profile → LLM answers) and work-auth resolver |
| `moonlighter-email` | `moonlighter.tracking` | Gmail sync and interview stage classification |
| `moonlighter` | `moonlighter.server` | FastMCP server — wires all packages together |

## Engineering

The pipeline applies for jobs with your name on them, so the bar is trust:

- **1171 tests, 100% branch coverage** — enforced as a CI gate (`--cov-fail-under=100`), not a dashboard number.
- **mypy strict** across all nine `moonlighter.*` packages; **ruff** with the security (`S`) ruleset on.
- **Lockstep releases** — the five packages must agree on version, pins and tag before anything uploads; the check runs before the build, because PyPI uploads are irreversible.
- **Protected main** — every change lands by pull request, with the CLA, the test suite and a security audit as required checks.
- **Curated, never invented** — answers come only from your profile; ambiguous fields (a salary in the wrong currency, an unclear visa question) are refused back to you instead of silently guessed.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
