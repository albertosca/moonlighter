> **[Leia em Português](https://github.com/albertosca/moonlighter/blob/main/packages/full/README.pt.md)**

# moonlighter

The whole job-hunting pipeline, driven from a Claude conversation. moonlighter scans job boards, scores every posting against **your** profile with an LLM, composes every answer an application form asks for, and tracks employer replies in your inbox — exposed to Claude as [MCP](https://modelcontextprotocol.io) tools, one `uvx moonlighter` away.

Two things it will **never** do: open a browser to fill a form, or submit an application for you. It prepares a reviewable answer sheet — the whole application, every question — and *you* paste and hit send. Your name goes on it; you stay in charge of it.

```bash
uvx moonlighter        # starts the MCP server
```

Then register it in Claude Code and talk to it: *"scan my companies"*, *"what's new above 7?"*, *"prepare the application for job 42"*. Setup, configuration and the full tool list live in the [repository README](https://github.com/albertosca/moonlighter#readme).

## What's inside

This is the umbrella distribution: it pins the four slices below in lockstep and adds the FastMCP server, the `moonlighter init` setup wizard, and the Claude Code plugin manifest.

| Package | What it is |
|---|---|
| **moonlighter** | ← you are here — everything below, wired into an MCP server |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Storage, config, profile and the LLM client — the foundation |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Job discovery across six ATS platforms, plus LLM fit-scoring |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Answer composition for application forms — you review, you submit |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Employer-reply tracking via Gmail, matched back to each application |

Everything runs on your machine, on your data, under your keys — there is no moonlighter server or account. See [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) and [DISCLAIMER.md](https://github.com/albertosca/moonlighter/blob/main/DISCLAIMER.md).

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
