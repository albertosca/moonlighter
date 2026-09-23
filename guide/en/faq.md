🇺🇸 [English](faq.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/faq/)

# FAQ

## Troubleshooting

- **The moonlighter tools don't show up in Claude** — MCP servers are read at session start: restart Claude Code (or open a new session) after registering.
- **`uvx moonlighter` runs an old version** — uvx caches environments; run `uvx --refresh moonlighter` once after a release.
- **Scan finds nothing** — check `company_list.yaml`: each entry needs the company's real ATS slug (the part in its careers URL), under the right source key. Test one company with `scan_company` before scanning everything.
- **LLM errors with `llm_backend: cli`** — the default backend shells out to the [Claude Code CLI](https://claude.ai/code); it must be installed and logged in. Switch to `llm_backend: api` + `ANTHROPIC_API_KEY` if you'd rather bill API credits.
- **"Missing profile / CV" warnings** — ask Claude to run `get_pipeline`: besides the funnel it reports exactly which setup file is missing and where it should live.
- **Gmail sync does nothing** — email tracking is optional and off until `setup_email` completes the OAuth flow; see the Gmail section above.

Still stuck? [Open a discussion](https://github.com/albertosca/moonlighter/discussions) — a report that includes what `get_pipeline` printed travels fastest.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
