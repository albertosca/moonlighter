🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/core/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/core/README.pt.md)

# moonlighter-core

The foundation of [moonlighter](https://albertosca.github.io/moonlighter/): the local storage, the configuration, your candidate profile and the LLM client that the other slices share. It has no command of its own; you get it with any of them.

![How moonlighter works](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

- **Storage** — a SQLite file under `MOONLIGHTER_HOME` (`~/.moonlighter` by default), no server and no account. Your pipeline is a file you can query.
- **Profile** — one `profile.yaml` that says who you are. Every answer the pipeline drafts starts from it, and `criteria` holds the hard and soft filters that drive scoring.
- **LLM client** — `llm_backend: cli` runs the Claude Code CLI on your Claude subscription; `llm_backend: api` uses the Anthropic SDK with your `ANTHROPIC_API_KEY`, read from the environment or from `~/.config/anthropic/api.env`.
- **Doctor** — every slice's `doctor` command reports, as JSON, where the state lives, whether the config loads, and which slices are installed.
- **Browser driver** — the optional `[browser]` extra, used only by browser-based scan extensions. The core flow never opens a browser.

## Part of moonlighter

| Package | What it is |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | Everything below, plus the MCP server for Claude — start here |
| **moonlighter-core** | ← you are here — storage, config, profile and the LLM client every slice shares |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Finds postings on seven ATS platforms and scores them against your profile |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Drafts the paste-ready answer sheet for one posting |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Matches employer replies in Gmail back to each application |

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). What leaves your machine is in [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md).
