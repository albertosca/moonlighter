🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/full/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/full/README.pt.md)

# moonlighter

**The job-application assistant that leaves the last word to you.**

moonlighter scans the job boards you choose, scores each posting against your profile, and drafts a complete answer sheet from your own data, flagging what it can't answer. It never opens the form and never clicks submit: you review the sheet, paste it, and send it yourself.

![How moonlighter works](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

## Start

```bash
uvx moonlighter          # the MCP server, for Claude Code
uvx moonlighter init     # a short wizard that writes config.yaml
```

Register it in Claude Code, then talk to it: *"scan my companies"*, *"what's new above 7?"*, *"prepare the application for job 42"*. Setup, configuration and every tool are in the [docs](https://albertosca.github.io/moonlighter/).

## What you get

- **A scored queue** — seven ATS platforms plus optional portals, each posting scored 0–10 against your profile and hard filters, with the reasoning kept.
- **One sheet per application** — every question the form asks, answered from your profile; a question it has no basis for comes back to you as a gap instead of a guess. Questions it recognises as salary, compliance or demographics are filled from your config or left for you, never answered by the model.
- **A tailored CV, if you want one** — a one-page LaTeX CV per posting, chosen from bullets you wrote.
- **Replies that find their application** — each sheet carries a tracking alias, and Gmail replies to it move that application forward.
- **An answer bank** — once an application is marked sent, its answers are offered again when the same question comes back.

## What's inside

This package pins the four slices below in lockstep and adds the MCP server, the `moonlighter init` wizard and the Claude Code plugin manifest. Every slice also installs alone, with a command-line tool that prints JSON — see [what each install gives you](https://albertosca.github.io/moonlighter/reference/cli/#what-each-install-gives-you).

| Package | What it is |
|---|---|
| **moonlighter** | ← you are here — everything below, plus the MCP server for Claude — start here |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Storage, config, profile and the LLM client every slice shares |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Finds postings on seven ATS platforms and scores them against your profile |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Drafts the paste-ready answer sheet for one posting |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Matches employer replies in Gmail back to each application |

moonlighter runs locally and calls your LLM; there is no moonlighter server or account. Your pipeline is a SQLite file under `~/.moonlighter`.

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). What leaves your machine is in [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md).
