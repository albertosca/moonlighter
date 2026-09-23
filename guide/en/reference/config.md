🇺🇸 [English](config.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/reference/config/)

# Configuration

`config.yaml` lives in `MOONLIGHTER_HOME` (default `~/.moonlighter/`); `uvx moonlighter init` writes a minimal one. This page covers the keys the guides mention. The full, commented surface is [`config.example.yaml`](https://github.com/albertosca/moonlighter/blob/main/config.example.yaml) in the repo. Relative paths in any key resolve under `MOONLIGHTER_HOME`; an absolute or `~`-prefixed path is used as given. An unknown key or a wrong-typed value is rejected at startup, with the key named, rather than silently ignored.

## Top-level keys

| Key | Default | What it does |
|---|---|---|
| `llm_backend` | `cli` | `cli` shells out to the Claude Code CLI (your Claude subscription); `api` uses the Anthropic SDK and needs `ANTHROPIC_API_KEY` |
| `score_threshold` | `6.5` | Jobs scoring below it are archived after a scan |
| `title_blocklist` | `[]` | Title substrings (case-insensitive) discarded before any LLM call |
| `answer_bank_max_age_days` | `90` | Days after its last submission that a banked answer stops being replayed; `null` disables expiry — see [Answer bank](../guides/answer-bank.md) |
| `portal_max_age_days` | `30` | Age at which portal-feed jobs (RemoteOK, Remotive, WeWorkRemotely, HN Who's Hiring), which can't be checked at their source, are archived; `0` disables it |

## cv

| Key | Default | What it does |
|---|---|---|
| `cv.default` | `cv.pdf` | The resume `prepare_application` names for the form's file-upload question |
| `cv.by_company` | `{}` | A different resume per company, matched case-insensitively by company name |
| `cv.pool` | `cv-pool.yaml` | The curated bullet pool; the [tailored CV](../guides/tailored-cv.md) turns on when this file exists |
| `cv.template_dir` | `cv-templates` | Holds `cv-template.en.tex` and, optionally, `cv-template.pt.tex` |
| `cv.generated_dir` | `cv-generated` | Where each job's tailored CV is cached, one directory per job id |

## email

Only for [Gmail tracking](../getting-started/gmail.md).

| Key | Default | What it does |
|---|---|---|
| `email.address` | none | The Gmail address you apply with; tracking aliases (`you+ref@gmail.com`) are minted from it, and the sync needs it |
| `email.credentials_path` | `gmail-client.json` | The OAuth client file from Google Cloud Console |
| `email.token_path` | `gmail-token.json` | Where `setup_email` saves (and overwrites) the token |
| `email.lookback_days` | `30` | How many days back the sync reads, read or unread |
| `email.mark_processed` | `false` | `true` labels processed mail in Gmail; by default deduplication stays in a local table |
| `email.processed_label` | `moonlighter/processed` | The label used when `mark_processed` is on |
| `email.archive_ref_matched` | `false` | Archive replies matched by alias that advanced an application |
| `email.archive_all_classified` | `false` | Also archive fuzzy and uncertain classified mail; unrelated mail is never touched |
| `email.interview_stages` | `[]` | Stage names a classified reply can set; the example file lists four, and a sync adds new stages the classifier proposes for the length of that run |

Labelling and archiving need the `gmail.modify` scope; `setup_email` asks you to consent again if your token is read-only.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
