# Disclaimer

## Third-Party Terms of Service

This tool interacts with job boards and applicant tracking systems (LinkedIn, Greenhouse, Lever,
Ashby, Workable, SmartRecruiters, Recruitee, and optionally Gupy), always through **your own
account/session**, to find and evaluate **real postings for your own applications** — never
scraping other candidates' data, never creating fake accounts, never sending bulk/spam
applications. The default interaction is read-only HTTP requests (discovery scans and, where an
ATS exposes it, reading a job's application-question schema). Driving a real browser is limited to
the optional `moonlighter-core[browser]` extra, used by browser-based scanner plugins (e.g. the
privately-distributed LinkedIn add-on) strictly for login and listing scans — never for filling in
or submitting a form; see [Browser Automation](#browser-automation) below and
[PRIVACY.md](PRIVACY.md). Use of these platforms is subject to their respective Terms of Service.
**You use this software at your own risk and are solely responsible for compliance with any
applicable ToS.** This section is a factual summary of public research, not legal advice — verify
against the current terms yourself before relying on it, especially since terms change over time.

**LinkedIn** — the User Agreement (§8.2) broadly and explicitly prohibits scraping and "bots or
other unauthorized automated methods," with no stated carve-out for personal, single-account,
non-commercial automation. This is the platform with the clearest, most direct prohibition of the
eight, and it deserves a sharper distinction between two different kinds of risk (researched
2026-07-22, see `docs/superpowers/specs/2026-07-22-linkedin-legal-risk-review.md` for the full
non-lawyer analysis and citations — not legal advice):

- **Litigation/criminal risk (e.g., under the U.S. Computer Fraud and Abuse Act) appears low** for a
  single individual automating their own, already-authenticated account. *Van Buren v. United
  States* (2021) narrowed the CFAA to accessing areas a user's own credentials are not entitled to
  reach at all — using otherwise-accessible features for a disfavored purpose is not, by itself, a
  CFAA violation. *hiQ Labs v. LinkedIn*, the case most often cited here, actually concerned
  logged-out scraping of public data (a different fact pattern) — and even hiQ still lost on
  LinkedIn's breach-of-contract claim. No reported case targets an individual for personal-use
  browser automation of their own account.
- **Contractual/practical risk (account restriction or suspension) is real and likely if detected**
  — LinkedIn's own Help Center documents this as the standard enforcement path, and it is
  self-executed by LinkedIn under the User Agreement, not a lawsuit.
- A dedicated technical alternative was researched and not found: LinkedIn's Talent/Jobs API
  program is not realistically obtainable by an individual developer, and the most visible
  third-party "licensed" LinkedIn job-data provider (Proxycurl) was sued by LinkedIn and shut down
  in 2025.
- One mitigation already built into the tool's architecture, worth naming explicitly: moonlighter
  never drives a browser to fill in or submit an application. `prepare_application` (or
  `prepare_application_from_paste`, when no API publishes the form's questions) composes an answer
  for every question it can, from your profile, and renders the whole application as one
  reviewable sheet — flagging anything it couldn't answer for you to fill in by hand. You paste
  the answers into the form and submit it yourself. This is human-supervised, assisted answer
  composition, not unattended bulk auto-apply — true for every ATS this tool talks to, including
  LinkedIn.

By using this tool against LinkedIn, you are choosing to accept that contractual/account risk
yourself — this project takes no responsibility for account restrictions LinkedIn may impose.

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

The shipped product never drives a browser to fill in or submit a form — see the LinkedIn bullet
above and [PRIVACY.md](PRIVACY.md) for how `prepare_application` composes answers for you to paste
in and submit yourself. Browser-driven form fill/submit was built and then deliberately moved off
the distributed product, onto a separate, paused branch (`feat/ats-automation`) not included in
any release.

The browser automation that *does* ship is narrower: the optional `moonlighter-core[browser]`
extra, used only by browser-based scanner plugins (e.g. the LinkedIn add-on) to log in and scan
listings. That is still automated interaction with a third-party platform, and the same ToS-risk
framing applies to it — excessive, abusive, or high-frequency scanning may result in your account
being flagged, rate-limited, or banned by the platform, same as the LinkedIn discussion above. Use
responsibly, keep scan frequency reasonable, and only for legitimate, single-account, personal use.

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

## No Affiliation, and Your Acknowledgment

moonlighter is not affiliated with, endorsed by, or sponsored by LinkedIn, Greenhouse, Lever,
Ashby, Workable, SmartRecruiters, Recruitee, Gupy, or any other platform it interacts with. Every
platform name mentioned here refers to that platform's own trademark, used solely to describe
interoperability.

There is no moonlighter service, server, or company — this is source code that **you** run
yourself, against **your own** accounts, at your own risk. By downloading, running, or otherwise
using this software, you acknowledge that automating a third-party platform may violate that
platform's own terms, that compliance with those terms is entirely your own responsibility, and
that you accept whatever consequences (up to and including account restriction) that platform may
impose as a result.
