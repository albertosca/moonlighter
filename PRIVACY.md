# Privacy & Data Handling

moonlighter is a **self-hosted, single-user tool** — there is no moonlighter server, account, or
company collecting your data. Everything described below runs on your own machine, under your own
control. This document explains what data the tool touches, where it lives, and what leaves your
machine.

## What is stored, and where

Everything lives under `MOONLIGHTER_HOME` (defaults to `~/.moonlighter/`) on your own disk, as
plain SQLite and files — never uploaded anywhere by moonlighter itself:

| Data | Location | Contents |
|------|----------|----------|
| Your candidate profile | `profile.yaml` | Name, contact info, work history, skills — whatever you put there. Read directly from disk each run; not copied elsewhere. |
| Job postings found | `moonlighter.db` (`Job` table) | Scraped listing text (company, title, description, salary if stated) — third-party content, not your personal data. |
| Your applications | `moonlighter.db` (`Application` table) | The form answers submitted on your behalf (`form_data`) — this **is** your personal data, since it's the same name/email/phone/etc. that went into the employer's form. Kept indefinitely; no automatic expiry. |
| Screenshots | `screenshots/<job_id>/` | Captured before/after filling and submitting, for your own review. These visibly contain whatever was on the page at that moment, including your filled-in answers. |
| Browser session | `browser-session/` | The Playwright/Chrome profile used for automation (cookies, local storage) — same as any browser profile. |
| Email sync dedup | `moonlighter.db` (`ProcessedEmail` table) | Only a Gmail message ID and a timestamp, so the sync doesn't reprocess the same email twice. **Not** the email body or subject — see below. |

None of this is encrypted at rest by moonlighter itself; it relies on your OS/disk-level
protections, same as any local application storing config files.

## What leaves your machine

- **Job-board/ATS requests** — HTTP requests and browser navigation to the platforms listed in
  [`DISCLAIMER.md`](DISCLAIMER.md), carrying whatever a normal browser session would send (your IP,
  user agent, and — during an application — the form data you're submitting to that specific
  employer, same as if you filled it in by hand).
- **LLM calls** — job descriptions and a filtered subset of your profile (see
  `profile_for_answers`/`_ANSWER_PROFILE_KEYS` in `base.py` — headline, summary, skills,
  experience, education, languages, publications; **not** salary targets, hard filters, or
  contact fields) are sent to Anthropic to generate application answers and score job fit, under
  whichever backend you configured (`llm_backend: cli` uses your own claude.ai session;
  `llm_backend: api` uses your own `ANTHROPIC_API_KEY`). See `DISCLAIMER.md` for Anthropic's Usage
  Policy.
- **Gmail** (optional, only if you run `setup_email`) — the sync reads your inbox via the Gmail
  API under your own OAuth credentials to detect interview-related emails. It is **read-only by
  default** (`mark_processed: false`) — it never modifies or labels your mail unless you opt in.
  The email **content itself is not persisted**: an LLM classifies each message in-memory and only
  a short generated summary (e.g. `"[2026-07-22] interview_scheduled: recruiter proposed a call
  Thursday"`) is written to the local `Application.notes` field — the raw subject/body never
  reaches the local database.

Nothing else is sent anywhere. There is no telemetry, analytics, or crash reporting.

## Deleting your data

Since everything lives under `MOONLIGHTER_HOME`, deleting it is a full data wipe:

```bash
rm -rf ~/.moonlighter
```

There is currently no built-in per-application or per-job deletion/retention tool — data
accumulates until you remove it manually or delete the whole directory. If you need finer-grained
deletion, the tables are plain SQLite (`moonlighter.db`) and can be queried/edited directly.

## Third-party data processors

moonlighter itself does not employ any third-party data processor. The services **you** configure
it to talk to — Anthropic (LLM calls), Google (Gmail API, if enabled), and each job platform you
apply through — are each independently responsible for their own handling of the data your
browser/API calls send them, under their own privacy policies. This document does not speak for
them.

## Not legal advice

This document describes the tool's actual behavior as of this writing, for your own transparency
and risk assessment. It is not a substitute for legal advice, and it is not a claim of compliance
with any specific regulation (LGPD, GDPR, CCPA, or otherwise) — see `DISCLAIMER.md` for the
related LGPD note on a not-yet-built Gupy applier.
