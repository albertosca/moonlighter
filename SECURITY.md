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

Untrusted content is wrapped in nonce-tagged delimiters before it reaches an LLM prompt
(`wrap_untrusted`), and everything the LLM returns from such a prompt is validated against a
closed set or clamped to a valid range before it can influence a decision. The LLM subprocess
itself runs with no tools, no MCP servers, no session persistence, and a neutral working
directory, so a successful injection has nothing to reach for.

## Known Accepted Risk

Commits in this repository carry the maintainer's personal email address as the git author
identity. This is a conscious choice, not an oversight — the address is already public on the
maintainer's other work. It is recorded here so that it reads as a decision rather than a leak.
