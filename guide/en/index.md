🇺🇸 [English](index.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/)

# moonlighter

**The job-application assistant that leaves the last word to you.**

Scans the job boards you choose, scores each posting against your profile, and drafts a complete answer sheet from your own data, flagging what it can't answer.

<!-- facts -->1,700+ tests · 100% branch coverage (CI-gated) · 5 packages on PyPI · mypy strict<!-- /facts -->

**[Get started →](getting-started/install.md)**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-dark.svg">
  <img alt="moonlighter scans, scores and drafts; only you paste and send the application" src="https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg">
</picture>

*moonlighter runs locally and calls your LLM: it scans boards, scores fit and drafts the sheet. Only you paste and send the application to the employer; the reply comes back matched by its `+alias`.*

## What it won't do

- **It never sends an application.** It drafts the sheet; you paste the answers into the employer's form and send it yourself.
- **Your pipeline lives in a local SQLite file.** Jobs, drafts and application history are stored under `MOONLIGHTER_HOME`. What leaves your machine is only what goes to the LLM and the APIs you configure — Claude, Gmail, the job boards. [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) lists every item.
- **The model never answers a question the guards recognise as salary, compliance or demographic.** Those come from your config or are left to you. The guards match known phrasings, and on the paste path the model still reads the whole page to find the questions.

The model can still get an answer wrong — which is why every sheet is yours to review.

## Where to go next

- [Install](getting-started/install.md) — requirements, the setup wizard, and registering the MCP server
- [Tailored CV](guides/tailored-cv.md) — a one-page LaTeX CV per posting, built from bullets you curated
- [Answer bank](guides/answer-bank.md) — screening answers you approved, reused on the next application
- [Command line](reference/cli.md) — a JSON CLI per package, for shells and cron jobs
- [MCP tools](reference/mcp-tools.md) — the 17 tools Claude calls on your behalf
- [Extensions](guides/extensions.md) — add a job source as a separate package

The decisions behind the design, and what each one cost, are on the [Engineering](engineering.md) page. Objections and fixes are in the [FAQ](faq.md).

---

Built by Alberto Cavalcanti — [LinkedIn](https://www.linkedin.com/in/albertosca/)
