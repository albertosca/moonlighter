🇺🇸 [English](faq.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/faq/)

# FAQ

Straight answers to the questions people ask before trusting a tool with their job applications, then fixes for the problems people hit most often.

## Questions

### Does moonlighter apply for me?

No. moonlighter never sends an application. It scans, scores and drafts a complete answer sheet; you paste the answers into the employer's form and send it yourself. It never opens the form and never clicks submit — the browser automation that once did was taken out of the product on 2026-08-12 (see [Engineering](engineering.md#stopped-driving-the-browser)).

### Can it get an answer wrong?

Yes — any LLM can. moonlighter narrows the room for it: answers are drafted from your profile, and the model is told to answer UNKNOWN when your profile gives it no basis, which comes back to you as a gap; questions the guards recognise as salary, compliance or demographic get your configured value or are left to you, never a drafted answer; and a free-text answer addressed to you instead of the employer is turned into a gap. None of that makes a drafted answer correct by construction, which is why you review every sheet before sending it.

### Does it work without Claude?

Partly. The [command-line tools](reference/cli.md) run from any shell or cron job without Claude as an MCP client, and `moonlighter-scan --no-eval` scans with no LLM call at all. Scoring postings, drafting answers and classifying replies need an LLM backend: Anthropic's, through the Claude Code CLI (`llm_backend: cli`) or the API (`llm_backend: api`), Cursor's, through the Cursor CLI (`llm_backend: cursor`), OpenAI's, through the Codex CLI (`llm_backend: codex`), or any provider you log in to in opencode (`llm_backend: opencode`). opencode can also be the MCP client in place of Claude: see [Install](getting-started/install.md).

### What leaves my machine?

Your pipeline — jobs, drafted answers, application history — is a local SQLite file under `MOONLIGHTER_HOME`. What leaves is what goes to the services you configure. To the LLM: job descriptions, a filtered subset of your profile, your CV pool's bullets when the [tailored CV](guides/tailored-cv.md) is on, and any page text you paste into `prepare_application_from_paste`. With `cli` or `api` that provider is Anthropic; with `cursor` it is Cursor and the model the account uses; with `codex` it is OpenAI and the model you name; with `opencode` it is the provider in the `provider/model` you name. Beyond that: read-only requests to the job boards, and, if you turn on [Gmail tracking](getting-started/gmail.md), your recent mail, read through the Gmail API and sent to the LLM to be classified. There is no moonlighter server and no telemetry. [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) has the details.

### What does an opencode call send and keep?

Each call runs `opencode run` once, in a private temporary directory, under a config moonlighter writes for that call: every tool, MCP server, skill and plugin is denied, your own opencode config and `AGENTS.md` files are not loaded, and the prompt goes over standard input. The prompt goes to the provider you named in `llm_model` / `eval_model`. opencode records each call as a session in its own database; moonlighter deletes that session when the call returns. A call that times out is killed and its output discarded, so moonlighter never reads its session id, and that one session stays in opencode's history.

## Troubleshooting

- **The moonlighter tools don't show up in Claude** — MCP servers are read at session start: restart Claude Code (or open a new session) after registering.
- **`uvx moonlighter` runs an old version** — uvx caches environments; run `uvx --refresh moonlighter` once after a release.
- **Scan finds nothing** — check `company_list.yaml`: each entry needs the company's real ATS slug (the part in its careers URL), under the right source key. Test one company with `scan_company` before scanning everything.
- **LLM errors with `llm_backend: cli`** — the default backend shells out to the [Claude Code CLI](https://claude.ai/code); it must be installed and logged in. Switch to `llm_backend: api` + `ANTHROPIC_API_KEY` if you'd rather bill API credits.
- **LLM errors with `llm_backend: cursor`** — the Cursor CLI (`agent`, or `cursor-agent`) must be installed, and `agent login` done.
- **LLM errors with `llm_backend: codex`** — the `codex` CLI must be installed and `codex login` done with a ChatGPT account (an API-key login is refused), and `llm_model` / `eval_model` must name models that account can run, not Claude ids.
- **"Missing profile / CV" warnings** — ask Claude to run `get_pipeline`: besides the funnel it reports exactly which setup file is missing and where it should live.
- **LLM errors with `llm_backend: opencode`** — the `opencode` CLI must be installed, `opencode auth login` done for the provider, and `llm_model` / `eval_model` written as `provider/model`, as `opencode models` lists them. At startup `get_pipeline` warns when opencode does not list a configured model, and when your opencode is not the 2.4 release moonlighter's call isolation was verified on.
- **The moonlighter tools don't show up in opencode** — run `opencode mcp list`; it should show `✓ moonlighter connected`. An entry without `"protocol": "2026-07-28"` fails the handshake, and one without `"codemode": false` hides the tools behind opencode's `execute` tool. The block to use is under Option C in [Install](getting-started/install.md).
- **Gmail sync does nothing** — email tracking is optional and off until `setup_email` completes the OAuth flow; see [Gmail tracking](getting-started/gmail.md).

Still stuck? [Open a discussion](https://github.com/albertosca/moonlighter/discussions) — a report that includes what `get_pipeline` printed travels fastest.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
