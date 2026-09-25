🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/scan/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/scan/README.pt.md)

# moonlighter-scan

The discovery slice of [moonlighter](https://albertosca.github.io/moonlighter/): it checks the job boards of the companies you list and scores each new posting against your profile, so you only read the ones worth reading.

![How moonlighter works](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

## Use it on its own

```bash
uvx moonlighter-scan                          # scan company_list.yaml, score new postings
uvx moonlighter-scan --company ashby trm-labs # one company's board
uvx moonlighter-scan --no-eval                # store postings unscored, no LLM call
uvx moonlighter-scan doctor
```

Every command prints one JSON document on stdout and exits `1` on a quiet day with nothing new, so it fits a cron job and `jq`.

- **Seven ATS platforms** — Greenhouse, Lever, Ashby, Recruitee (custom career domains included), Workable, SmartRecruiters and InHire.
- **Optional portals** — Gupy, RemoteOK, Remotive, We Work Remotely and HN Who's Hiring, off until you enable them, filtered by keyword.
- **Scored with the reasoning kept** — each posting gets 0–10 against your profile and hard filters; below your threshold it is archived, with the verdict kept.
- **Cheap cuts first** — titles on your blocklist, and on-site or hybrid postings outside the `criteria.home_city` you set in your profile, are archived before any LLM call.
- **Closed postings archived** — jobs that disappeared from their board are archived on the next scan.
- **One row per job** — URLs are normalised, so the same posting found twice stays one job.

## Works better with

With [moonlighter-apply](https://pypi.org/project/moonlighter-apply/), one script scans, picks by score and prepares a sheet for each pick. With [moonlighter](https://pypi.org/project/moonlighter/), you ask Claude instead.

| Package | What it is |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | Everything below, plus the MCP server for Claude — start here |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Storage, config, profile and the LLM client every slice shares |
| **moonlighter-scan** | ← you are here — finds postings on seven ATS platforms and scores them against your profile |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Drafts the paste-ready answer sheet for one posting |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Matches employer replies in Gmail back to each application |

## License

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contributions require signing the [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). What leaves your machine is in [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md).
