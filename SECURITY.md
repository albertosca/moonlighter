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

The job description and email bodies are wrapped in nonce-tagged delimiters
(`wrap_untrusted`) before they reach an LLM prompt. Scraped form-field labels and dropdown
option texts — also untrusted, sourced from the ATS page DOM — currently reach the prompt
unwrapped (`packages/apply/gauntler/application/appliers/base.py`,
`packages/apply/gauntler/application/answers/option_matcher.py`); closing that gap is tracked
as follow-up work, not covered by this document's guarantees.

Output validation is not uniform either. Evaluation scores are clamped to a valid range and
salary source and email-pipeline stage are checked against a closed set. The dropdown-picker
LLM returns an index rather than free text, so the chosen value is always constrained to a
real on-page option. The free-text answers an LLM writes into application form fields,
however, are not closed-set validated or clamped — they are typed into the form as returned.
A human operator reviews and explicitly confirms before any application is actually
submitted, which gates that gap at the point of consequence.

The LLM subprocess itself runs with no tools, no MCP servers, no session persistence, and a
neutral working directory, so a successful prompt injection has nothing to reach for beyond
whatever a given prompt already validates or a human catches at confirmation.

## Known Accepted Risk

Commits in this repository carry the maintainer's personal email address as the git author
identity. This is a conscious choice, not an oversight — the address is already public on the
maintainer's other work. It is recorded here so that it reads as a decision rather than a leak.
