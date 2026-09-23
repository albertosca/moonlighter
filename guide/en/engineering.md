🇺🇸 [English](engineering.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/engineering/)

# Engineering

moonlighter drafts job applications that go out under your name, so the bar is trust. This page records the design decisions behind that bar, what each one cost, and where to check it in the code.

## Decisions and the trade-offs we accepted

| Decision | Trade-off accepted |
|---|---|
| Stopped driving the browser | Every application costs you a paste and a click |
| Deterministic guards around the drafting step | They recognise known phrasings only |
| Model text escaped into the CV's LaTeX, never validated | Model output can't carry LaTeX formatting beyond bold |
| Five slices with a tested import boundary and lockstep releases | Every release bumps five packages by hand |
| 100% branch coverage as a gate, gates proven by canaries | Every new branch costs a test |

### Stopped driving the browser

moonlighter used to fill ATS forms in a real browser. On 2026-08-12 ([`37b1ac2`](https://github.com/albertosca/moonlighter/commit/37b1ac2)) those browser appliers left `main` for their own branch, and the product became assisted: it drafts the whole answer sheet, and you paste it into the form and send it. The cost is a manual step on every application. What it buys: the tool cannot send anything under your name, and it no longer depends on form markup, captchas and platform rules it doesn't control.

### Deterministic guards around the drafting step

Some questions should not be answered by a model at all. Before drafting, plain code recognises salary questions (answered from your configured target, or flagged when the units disagree — [`field_map.py`](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/answers/field_map.py)), compliance declarations (always left to you — [`compliance.py`](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/answers/compliance.py)) and demographic self-identification (answered only from what you wrote in `profile.yaml`, otherwise left to you). After drafting, [`composer.py`](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/assisted/composer.py) turns any answer addressed to the operator ("the candidate should provide…") into a gap. The trade-off: the guards match known phrasings, so an unusual wording can slip past them — the salary rule's own comments record earlier versions that did. That is one more reason every sheet is reviewed.

### Model text escaped, never validated, into the CV's LaTeX

The tailored CV compiles model-written text with `pdflatex`, which makes that text a code-injection surface. Two earlier designs let the model's translations carry LaTeX and tried to validate it; both were bypassed. The instructive bypass was `^^5c`: TeX turns it into a backslash while tokenising, so no check for a literal backslash sees it, and `\input{...}` could then embed a local file into the PDF you upload to an employer. Now [`escape_latex`](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/cvgen/render.py) rewrites every TeX special character, `^` included, so there is nothing left to detect. The cost: model output can't carry formatting beyond `**bold**`.

### Five slices with a tested import boundary and lockstep releases

The five PyPI packages each install on their own, and a `pip install moonlighter-scan` gets only the dependencies its `pyproject.toml` declares. An import that reaches into an undeclared package still works in the monorepo and breaks for the user who installed one slice — measured on 2026-09-14 against the published artifact. [`tests/test_package_boundaries.py`](https://github.com/albertosca/moonlighter/blob/main/tests/test_package_boundaries.py) now walks every import with Python's `ast` module and fails on any that crosses an undeclared boundary. Versions move in lockstep by hand: [`scripts/check_version_lockstep.py`](https://github.com/albertosca/moonlighter/blob/main/scripts/check_version_lockstep.py) is the first step of the CI test job, and the publish workflow refuses a tag that doesn't match the packaged version — because a PyPI upload can't be taken back.

### 100% branch coverage as a gate, gates proven by canaries

`--cov-fail-under=100` sits in `pyproject.toml`, so the test suite fails on any branch no test runs. The cost is a test for every new branch. A gate is only trusted after it has been made to fail on purpose (a canary): for example, the security lint (ruff's `S` rules) was trusted as a blocking gate only after CI rejected an injected `shell=True` call. A check that has never failed may not be checking anything.

## What the model never answers

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://albertosca.github.io/moonlighter/assets/diagrams/llm-guards-dark.svg">
  <img alt="Before drafting, recognised salary, compliance and demographic questions go to your config or to you; after drafting, answers addressed to the operator become gaps" src="https://albertosca.github.io/moonlighter/assets/diagrams/llm-guards-light.svg">
</picture>

*Two checkpoints. Before drafting, a question the guards recognise as salary, compliance or demographic gets your configured value or is left as a gap for you. After drafting, an answer addressed to the operator becomes a gap. Only the rest reaches the sheet. The guards match known phrasings, and on the paste path the model still reads the whole page to find the questions.*

## Architecture

A [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) of 5 namespace packages (`moonlighter.*`), feature-sliced:

| Package | Namespace | Purpose |
|---------|-----------|---------|
| `moonlighter-core` | `moonlighter.core` | DB (Peewee/SQLite), config, optional browser driver (`[browser]` extra), LLM client |
| `moonlighter-scan` | `moonlighter.discovery` | ATS scrapers and LLM-based job scoring |
| `moonlighter-apply` | `moonlighter.application` | Answer composer (curated profile → LLM answers) and work-auth resolver |
| `moonlighter-email` | `moonlighter.tracking` | Gmail sync and interview stage classification |
| `moonlighter` | `moonlighter.server` | FastMCP server — wires all packages together |

## Quality gates

- **Test suite with 100% branch coverage** — the current test count is on the [README's proof line](https://github.com/albertosca/moonlighter#readme), checked by CI; coverage is enforced as a CI gate (`--cov-fail-under=100`), not a dashboard number.
- **mypy strict** across all nine `moonlighter.*` packages; **ruff** with the security (`S`) ruleset on.
- **Lockstep releases** — the five packages must agree on version, pins and tag before anything uploads; the check runs before the build, because PyPI uploads are irreversible.
- **Protected main** — every change lands by pull request, with the CLA, the test suite and a security audit as required checks.
- **Drafted from your profile, gaps flagged** — answers are drafted only from your profile; a question with no basis there, or an ambiguous field (a salary in the wrong currency, an unclear visa question), comes back to you as a gap instead of a guess. The model can still get an answer wrong, which is why you review every sheet.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
