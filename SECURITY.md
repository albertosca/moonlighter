# Security Policy

## Supported Versions

This project is pre-1.0 and does not maintain a support matrix. Only the latest commit on
`main` receives security fixes.

## Reporting a Vulnerability

Please report security vulnerabilities privately, through GitHub Security Advisories:
open this repository's **Security** tab and choose **Report a vulnerability**. That opens a
private channel visible only to the maintainers.

**Do not open a public issue for a security report.** Public issues are visible to everyone,
including before a fix exists.

## Trust Model

This project drives an LLM and a real browser over content it did not write — job
descriptions, ATS pages, recruiter emails. The boundary between those and the agent is the
whole security story.

**Trusted:**
- The human operator.
- Local YAML configuration, including the paths to the `claude` CLI binary and the browser
  binary. Anyone who can write that file can already run code as the operator.

**Conditionally trusted:**
- The orchestrating Claude session. It decides which tools to invoke; it is the boundary at
  which a tool call is authorized, and destructive or outward-facing tools gate on explicit
  operator confirmation.

**Untrusted — treated as data, never as instructions:**
- Job descriptions and any scraped page text.
- The DOM of ATS application pages.
- Email bodies fetched during application tracking.

Untrusted content is wrapped in nonce-tagged delimiters (`wrap_untrusted`) before it reaches an
LLM prompt: the job description, email bodies, scraped form-field labels, and scraped dropdown
option texts. The wrapper strips any literal copy of its own tag from the text before wrapping,
and the tag carries a random per-call nonce, so content that tries to close the block early or
replay a tag it saw before does not escape.

Output validation is closed-set wherever a closed set exists. Evaluation scores are clamped to a
valid range; salary source and email-pipeline stage are checked against fixed whitelists; the
dropdown picker returns an index, so its choice is always a real on-page option; and the keys of
the form-answer map resolve against the fields actually present on the page — a key the model
invents cannot enter. What is *not* closed-set validated, and cannot be, are the free-text answers
the model writes into form fields: they are prose. Two things gate them. A field the model fails
to answer becomes a review sentinel rather than going into the form blank, and a human operator
reviews and explicitly confirms every application before it is submitted.

The LLM subprocess itself runs with no tools, no MCP servers, no session persistence, and a
neutral working directory, so a successful prompt injection has nothing to reach for. The CLI
binary is resolved to an absolute path rather than through `PATH`. Note that ruff's `S`
(flake8-bandit) lint gate does not analyze `asyncio.create_subprocess_exec` — the properties of
that launch (absolute path, list form, no shell, prompt over stdin) are locked by a dedicated
test instead of by the linter.

## Known Accepted Risk

Commits in this repository carry the maintainer's personal email address as the git author
identity. This is a conscious choice, not an oversight — the address is already public on the
maintainer's other work. It is recorded here so that it reads as a decision rather than a leak.
