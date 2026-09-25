🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/apply/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/apply/README.pt.md)

# moonlighter-apply

The answering slice of [moonlighter](https://albertosca.github.io/moonlighter/): for one posting, it gathers every question the application form asks and drafts an answer to each from your profile, as one sheet you review and paste. **It never opens the form and never submits.**

![How moonlighter works](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

## Use it on its own

```bash
uvx moonlighter-apply prepare 42                    # questions from the job's ATS API
uvx moonlighter-apply prepare 42 --paste page.txt   # questions read from text you copied
uvx moonlighter-apply prepare --url https://...     # ingest a posting by URL, then prepare
uvx moonlighter-apply doctor
```

Every command prints one JSON document on stdout.

- **The real questions** — where the ATS publishes its form (Greenhouse, Recruitee), the questions, required flags and options come straight from its API.
- **Any other form** — paste the page text and the questions are read from it; this works on any ATS, login walls included.
- **Gaps instead of guesses** — answers are drafted from a filtered part of your profile. A question it has no basis for comes back to you as a gap, and questions it recognises as salary, compliance or demographics are filled from your config or left for you, never answered by the model.
- **A tailored CV, if you want one** — a one-page LaTeX CV for the posting, its bullets chosen from a pool you wrote; `bootstrap-cv` drafts a first pool from your profile.
- **Tracking built in** — each sheet carries the application's tracking alias.

## Works better with

With [moonlighter-email](https://pypi.org/project/moonlighter-email/), replies to that alias move the application forward. With [moonlighter-scan](https://pypi.org/project/moonlighter-scan/), you prepare sheets straight from the scored queue.

| Package | What it is |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | Everything below, plus the MCP server for Claude — start here |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Storage, config, profile and the LLM client every slice shares |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Finds postings on seven ATS platforms and scores them against your profile |
| **moonlighter-apply** | ← you are here — drafts the paste-ready answer sheet for one posting |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Matches employer replies in Gmail back to each application |

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). What leaves your machine is in [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md).
