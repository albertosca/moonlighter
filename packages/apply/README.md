> **[Leia em Português](https://github.com/albertosca/moonlighter/blob/main/packages/apply/README.pt.md)**

# moonlighter-apply

The answering slice of moonlighter: it reads every question an application form asks and composes an answer for each one, curated from your profile — then renders the whole thing as one reviewable sheet. You read it, you paste it, you hit send. **It never opens a browser, never touches the form, never submits.**

![How moonlighter works](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

Docs: https://albertosca.github.io/moonlighter/

- **Form questions from the source** — where the ATS publishes its form schema (Greenhouse, Recruitee), `prepare_application` fetches the real questions, required flags and options straight from the API.
- **Any other form** — `prepare_application_from_paste` does the same from text you copy off the page yourself; works on any ATS, login walls included.
- **Drafted from your profile, gaps flagged** — answers are drafted from a filtered subset of your profile; the model is told to answer UNKNOWN when the profile gives it no basis, and that question comes back to you as a gap.
- **Refuses over converts** — an ambiguous field (a salary in the wrong currency, an unclear work-auth question) is returned for your review instead of silently guessed.
- **Tracking built in** — each sheet carries the application's tracking alias, so the reply lands back in your pipeline (see [moonlighter-email](https://pypi.org/project/moonlighter-email/)).

## Part of moonlighter

You rarely install this slice alone — [moonlighter](https://pypi.org/project/moonlighter/) pins it together with its three siblings and wires everything into an MCP server for Claude (`uvx moonlighter`).

| Package | What it is |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | The whole pipeline as an MCP server — start here |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Storage, config, profile, LLM client — the foundation |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Job discovery across seven ATS platforms, plus LLM fit-scoring |
| **moonlighter-apply** | ← you are here — answer composition; you review, you submit |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Employer-reply tracking via Gmail, matched back to each application |

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
