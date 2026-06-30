# Disclaimer

## Terms of Service

This tool interacts with job boards (LinkedIn, Greenhouse, Lever, Ashby) by driving a real browser
or making HTTP requests. Use of these platforms is subject to their respective Terms of Service.
Automated or programmatic access may violate those terms. **You use this software at your own
risk and are solely responsible for compliance with any applicable ToS.**

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
