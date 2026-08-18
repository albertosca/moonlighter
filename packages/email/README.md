> **[Leia em Português](https://github.com/albertosca/moonlighter/blob/main/packages/email/README.pt.md)**

# moonlighter-email

The tracking slice of moonlighter: it watches your Gmail for employer replies, matches each one back to the application that caused it, and moves your pipeline forward — so "did they ever answer?" is a query, not an archaeology dig.

- **Matched by tracking alias** — each application carries its own reply-to alias, so a rejection, an ack or an interview invite lands on the right application automatically.
- **Classified by LLM, in memory** — each message is classified (interview scheduled, rejection, offer…) and only a one-line summary is persisted; **the raw subject and body never reach the local database.**
- **Read-only by default** — your own Gmail OAuth credentials, no label or state touched unless you opt in.
- **Pipeline view** — statuses roll up into a funnel you can ask Claude about: what's waiting, what's moving, what went silent.

## Part of moonlighter

You rarely install this slice alone — [moonlighter](https://pypi.org/project/moonlighter/) pins it together with its three siblings and wires everything into an MCP server for Claude (`uvx moonlighter`).

| Package | What it is |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | The whole pipeline as an MCP server — start here |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Storage, config, profile, LLM client — the foundation |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Job discovery across six ATS platforms, plus LLM fit-scoring |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Answer composition for application forms — you review, you submit |
| **moonlighter-email** | ← you are here — employer-reply tracking via Gmail |

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
