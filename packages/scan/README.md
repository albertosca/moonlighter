> **[Leia em Português](https://github.com/albertosca/moonlighter/blob/main/packages/scan/README.pt.md)**

# moonlighter-scan

The discovery slice of moonlighter: it sweeps the job boards you care about and hands you only the postings worth your time — each one scored against **your** profile by an LLM, with the reasoning written down.

- **Six ATS platforms** — Greenhouse, Lever, Ashby, Recruitee (custom career domains included), Workable and SmartRecruiters, driven by a company list you configure.
- **Optional portals** — RemoteOK, Remotive, WeWorkRemotely and HN Who's Hiring, config-gated off by default, with keyword filtering.
- **Ad-hoc scans** — point `scan_company` at any company slug ("what's open at trm-labs on Ashby?") without touching your config.
- **LLM evaluation** — every new posting is scored against your profile and hard filters; below-threshold jobs are archived automatically, with the verdict kept for audit.
- **Dedup that holds** — URL-normalized, so the same job through two doors stays one row.

## Part of moonlighter

You rarely install this slice alone — [moonlighter](https://pypi.org/project/moonlighter/) pins it together with its three siblings and wires everything into an MCP server for Claude (`uvx moonlighter`).

| Package | What it is |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | The whole pipeline as an MCP server — start here |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Storage, config, profile, LLM client — the foundation |
| **moonlighter-scan** | ← you are here — job discovery and LLM fit-scoring |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Answer composition for application forms — you review, you submit |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Employer-reply tracking via Gmail, matched back to each application |

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
