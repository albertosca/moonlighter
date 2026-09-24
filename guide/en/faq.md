🇺🇸 [English](faq.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/faq/)

# FAQ

Straight answers to the questions people ask before trusting a tool with their job applications, then fixes for the problems people hit most often.

## Questions

### Does moonlighter apply for me?

No. moonlighter never sends an application. It scans, scores and drafts a complete answer sheet; you paste the answers into the employer's form and send it yourself. It never opens the form and never clicks submit — the browser automation that once did was taken out of the product on 2026-08-12 (see [Engineering](engineering.md#stopped-driving-the-browser)).

### Can it get an answer wrong?

Yes — any LLM can. moonlighter narrows the room for it: answers are drafted from your profile, and the model is told to answer UNKNOWN when your profile gives it no basis, which comes back to you as a gap; questions the guards recognise as salary, compliance or demographic get your configured value or are left to you, never a drafted answer; and a free-text answer addressed to you instead of the employer is turned into a gap. None of that makes a drafted answer correct by construction, which is why you review every sheet before sending it.

### Does it work without Claude?

Partly. The [command-line tools](reference/cli.md) run from any shell or cron job without Claude as an MCP client, and `moonlighter-scan --no-eval` scans with no LLM call at all. Scoring postings, drafting answers and classifying replies need an LLM backend: today that is Anthropic's, through the Claude Code CLI (`llm_backend: cli`) or the API (`llm_backend: api`).

### What leaves my machine?

Your pipeline — jobs, drafted answers, application history — is a local SQLite file under `MOONLIGHTER_HOME`. What leaves is what goes to the services you configure. To the LLM (Claude): job descriptions, a filtered subset of your profile, your CV pool's bullets when the [tailored CV](guides/tailored-cv.md) is on, and any page text you paste into `prepare_application_from_paste`. Beyond that: read-only requests to the job boards, and, if you turn on [Gmail tracking](getting-started/gmail.md), your recent mail, read through the Gmail API and sent to the LLM to be classified. There is no moonlighter server and no telemetry. [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) has the details.

## Troubleshooting

- **The moonlighter tools don't show up in Claude** — MCP servers are read at session start: restart Claude Code (or open a new session) after registering.
- **`uvx moonlighter` runs an old version** — uvx caches environments; run `uvx --refresh moonlighter` once after a release.
- **Scan finds nothing** — check `company_list.yaml`: each entry needs the company's real ATS slug (the part in its careers URL), under the right source key. Test one company with `scan_company` before scanning everything.
- **LLM errors with `llm_backend: cli`** — the default backend shells out to the [Claude Code CLI](https://claude.ai/code); it must be installed and logged in. Switch to `llm_backend: api` + `ANTHROPIC_API_KEY` if you'd rather bill API credits.
- **"Missing profile / CV" warnings** — ask Claude to run `get_pipeline`: besides the funnel it reports exactly which setup file is missing and where it should live.
- **Gmail sync does nothing** — email tracking is optional and off until `setup_email` completes the OAuth flow; see [Gmail tracking](getting-started/gmail.md).

Still stuck? [Open a discussion](https://github.com/albertosca/moonlighter/discussions) — a report that includes what `get_pipeline` printed travels fastest.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
