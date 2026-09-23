🇺🇸 [English](cli.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/reference/cli/)

# Command line

## Command line

Every slice also installs a command you can drive from a shell or a cron job, with no LLM conversation involved. Each prints exactly one JSON document on stdout (logs go to stderr) and exits `0` on success, `1` when there was nothing to do (no new jobs, job not found, no questions), `2` on a usage or config error, `3` on an unexpected error (the JSON then carries `kind: "error"` and the traceback goes to stderr).

| Command | What it does |
|---|---|
| `moonlighter-scan [--phase all] [--keywords ...]` | Run a scan; `--company SOURCE SLUG` scans one board. `--no-eval` discovers and stores postings as `needs_review` without calling the LLM — score them later with `verify_job`. |
| `moonlighter-apply prepare JOB_ID [--paste FILE]` | Compose the paste-ready sheet; `--paste -` reads the page text from stdin. |
| `moonlighter-apply prepare --url URL [--company X --title Y] [--paste FILE]` | Ingest the posting first: through its ATS API when the URL has a known shape, otherwise from the page itself with `--company` and `--title` supplied; stored unscored, then prepared. No LLM call for the ingest. |
| `moonlighter-email sync` | Classify recent replies and advance applications. Standalone it does not feed the answer bank; the MCP server's `sync_email_responses` does. |
| `moonlighter-email register JOB_ID` | Mark a job as applied by hand and mint its `+ref` tracking alias, so replies to it are matched by `sync`. |
| `moonlighter-scan doctor` · `moonlighter-apply doctor` · `moonlighter-email doctor` · `moonlighter doctor` | Where the state lives and whether the config loads, as JSON; exit `1` when the config is missing or invalid. |

```sh
moonlighter-scan --no-eval | jq '.saved[] | select(.status == "needs_review") | .url'
```

The example above exits `1` on every quiet day (no new jobs), which trips `set -e`/`pipefail` in a script that chains it with `jq` — check the exit code before treating that as a script failure. `--no-eval` is zero-**LLM**, not offline: `archive_stale_jobs` still makes HTTP requests to check whether previously-saved jobs closed.

### What each install gives you

The five packages are slices of one tool. Install the ones you need; each command tells you in `--help` what it can do here and what a missing slice would add, and `doctor` prints the same as JSON.

| You install | You get |
|---|---|
| `moonlighter-scan` | `moonlighter-scan`: boards and portals scanned, postings scored (or stored unscored with `--no-eval`), closed ones archived |
| `moonlighter-apply` | `moonlighter-apply prepare`: the paste-ready sheet, from a job id or straight from a URL |
| `moonlighter-email` | `moonlighter-email register` and `sync`: applications registered by hand, Gmail replies matched back to them |
| `moonlighter-scan` + `moonlighter-apply` | one script: scan, pick by score, prepare a sheet for each |
| `moonlighter-apply` + `moonlighter-email` | the tracking alias a sheet mints is the one `sync` matches replies against |
| `moonlighter` (everything) | all of the above plus the MCP server for Claude Code, and answer-bank promotion when a reply advances an application |

```sh
moonlighter-apply doctor | jq '.slices, .capabilities.missing[].name'
```

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
