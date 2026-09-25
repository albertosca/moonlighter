🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/email/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/email/README.pt.md)

# moonlighter-email

The tracking slice of [moonlighter](https://albertosca.github.io/moonlighter/): it reads your Gmail for employer replies, matches each one to the application it answers, and moves that application forward, so "did they ever reply?" has an answer.

![How moonlighter works](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

## Use it on its own

```bash
uvx moonlighter-email register 42   # mark job 42 as applied and mint its tracking alias
uvx moonlighter-email sync          # read recent replies and advance the applications
uvx moonlighter-email doctor
```

Every command prints one JSON document on stdout.

- **Matched by tracking alias** — each application gets its own `+ref` address, so a rejection, an acknowledgement or an interview invite lands on the right application.
- **Classified, not stored** — the LLM classifies each reply in memory and only a one-line summary is kept; the subject and body never reach the local database.
- **Read-only by default** — your own Gmail OAuth credentials; nothing is marked or archived unless you turn it on.

## Works better with

With [moonlighter-apply](https://pypi.org/project/moonlighter-apply/), the sheet you paste already carries the application's alias. With [moonlighter](https://pypi.org/project/moonlighter/), a reply that advances an application also saves its answers to the answer bank.

| Package | What it is |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | Everything below, plus the MCP server for Claude — start here |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Storage, config, profile and the LLM client every slice shares |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Finds postings on seven ATS platforms and scores them against your profile |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Drafts the paste-ready answer sheet for one posting |
| **moonlighter-email** | ← you are here — matches employer replies in Gmail back to each application |

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). What leaves your machine is in [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md).
