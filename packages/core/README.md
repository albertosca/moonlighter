> **[Leia em Português](https://github.com/albertosca/moonlighter/blob/main/packages/core/README.pt.md)**

# moonlighter-core

The foundation every other moonlighter slice stands on: the SQLite storage (Peewee models for jobs, applications and processed emails), the `MOONLIGHTER_HOME` configuration layer, your candidate profile, and the LLM client the whole pipeline shares.

- **Storage** — plain SQLite under `~/.moonlighter/`, no server, no account. Your data stays yours, greppable on your own disk.
- **Profile** — one `profile.yaml` describing who you are; every answer the pipeline composes is curated from it, never invented past it.
- **LLM client** — switchable per config between the Claude Code CLI (billed to your Claude subscription, no API key) and the Anthropic SDK (your `ANTHROPIC_API_KEY`).
- **Browser driver** — optional `[browser]` extra, used only by browser-based scan extensions. The core product never needs it.

## Part of moonlighter

You rarely install this slice alone — [moonlighter](https://pypi.org/project/moonlighter/) pins it together with its three siblings and wires everything into an MCP server for Claude (`uvx moonlighter`).

| Package | What it is |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | The whole pipeline as an MCP server — start here |
| **moonlighter-core** | ← you are here — storage, config, profile, LLM client |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Job discovery across six ATS platforms, plus LLM fit-scoring |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Answer composition for application forms — you review, you submit |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Employer-reply tracking via Gmail, matched back to each application |

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
