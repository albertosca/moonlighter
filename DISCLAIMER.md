# Disclaimer

## Terms of Service

This tool interacts with job boards and applicant tracking systems (LinkedIn, Greenhouse, Lever,
Ashby, Workable, SmartRecruiters, Recruitee, and optionally Gupy) by driving a real browser or
making HTTP requests, always through **your own account/session**, applying to **real postings on
your own behalf** — never scraping other candidates' data, never creating fake accounts, never
sending bulk/spam applications. Use of these platforms is subject to their respective Terms of
Service. **You use this software at your own risk and are solely responsible for compliance with
any applicable ToS.** This section is a factual summary of public research, not legal advice —
verify against the current terms yourself before relying on it, especially since terms change
over time.

**LinkedIn** — the User Agreement (§8.2) broadly and explicitly prohibits scraping and "bots or
other unauthorized automated methods," with no stated carve-out for personal, single-account,
non-commercial automation. This is the platform with the clearest, most direct prohibition of the
eight. Publicly reported enforcement ranges from rate-limiting/CAPTCHA challenges to account
restriction or suspension.

**Greenhouse, Lever, Ashby, Workable, Recruitee** — none of these publish a candidate-facing Terms
of Use that explicitly names bots, scraping, or automated form submission. Where a Terms document
exists at all on the candidate-facing side, it is typically framed as a contract between the
*employer* (the paying customer) and the ATS vendor — applicants are referenced only as data
subjects, not as a contracting party bound by acceptance terms. **Absence of an explicit
prohibition is not the same as permission** — general anti-abuse clauses (server impairment,
unauthorized access, circumventing security measures) still apply and could plausibly be read to
cover abusive automation, even if none of them name "bots" or "automation" directly. Greenhouse
additionally uses invisible reCAPTCHA on its submit action (configurable per employer), which can
trigger an email-verification challenge.

**SmartRecruiters** — the Candidate Terms of Use prohibits "automatic means to access content or
data from *other users*" and harvesting others' data, which most naturally reads as a
cross-account-scraping restriction rather than a ban on automating your own application — but this
is an interpretive reading, not a settled one. SmartRecruiters also runs DataDome bot-detection on
its registration/application endpoints; DataDome's public case study with SmartRecruiters
describes distinguishing legitimate automated submissions from abusive ones via allowlisting, not
blocking all automation outright.

**Gupy** (not yet built — see `BACKLOG.md`) — the candidate Terms of Use similarly has no explicit
bot/automation clause; the closest language covers unauthorized security testing, content
duplication, and server overload. The account is stated to be "individual and non-transferable,"
which is a relevant consideration for a tool that would need to authenticate as the candidate.

## Data Protection (LGPD) — Gupy / CPF

If a Gupy applier is ever built, it would handle the user's own CPF (Brazilian tax ID) to fill
Gupy's candidate portal. Under LGPD (Lei 13.709/2018), **CPF is ordinary personal data, not
"sensitive personal data"** (the sensitive category, Art. 5º II, is limited to racial/ethnic
origin, religious/political/union affiliation, health, sex life, and genetic/biometric data) — so
the heightened Art. 11 consent regime does not apply. General LGPD obligations (purpose
limitation, data minimization, security duty under Art. 46) still apply to whoever processes the
data. LGPD's Art. 4º I carves out processing "by a natural person exclusively for personal,
non-economic purposes" — relevant if this tool is built and used strictly by/for a single
individual on their own data, not distributed as a hosted service acting on multiple people's
data. This is not legal advice; consult a qualified professional before building or shipping
that applier.

## Browser Automation

This tool automates form submission in job application portals. Excessive, abusive, or
high-frequency use may result in your account being flagged, rate-limited, or banned by the
platform. Use responsibly and only for legitimate, human-supervised job applications.

## LLM Backend — `cli` mode

When `llm_backend: cli` is set, the tool invokes the Claude Code CLI and drives **your personal
claude.ai session** to generate answers and evaluations. This means:

- Prompts and job data are sent to Anthropic's servers under your account.
- Anthropic's [Usage Policy](https://www.anthropic.com/legal/usage-policy) applies.
- For production, shared, or API-billed use, set `llm_backend: api` and provide an
  `ANTHROPIC_API_KEY` — this gives explicit billing control and removes the session dependency.

## No Warranty

This software is provided "as is", without warranty of any kind, express or implied. The authors
are not liable for any damages, account bans, missed opportunities, or other consequences arising
from use of this software. See [LICENSE](LICENSE) for the full terms under the GNU Affero General
Public License v3.
