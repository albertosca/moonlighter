🇺🇸 [English](first-scan.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/getting-started/first-scan/)

# Your first scan

From an empty pipeline to a paste-ready application in one Claude conversation. This assumes you finished [Install](install.md): `config.yaml` written, `profile.yaml` and `company_list.yaml` filled in, and the MCP server registered.

## How to scan the companies you care about

1. **List the companies.** In `company_list.yaml`, put each company under its ATS (`greenhouse`, `lever`, `ashby`, `workable`, `recruitee`, `smartrecruiters`, `inhire`) and a phase (`phase1`, `phase2`, `phase3`); a plain list with no phases is scanned in every phase. The slug is the company's identifier in its job-board URL: for `https://boards.greenhouse.io/acme` it is `acme`.
2. **Try one company first.** Ask Claude "what's open at acme on Greenhouse?". That runs `scan_company`, which scans one board without touching your list — a wrong slug shows up here, not in the middle of a full scan.
3. **Scan your list.** Ask "scan my companies". That runs `scan_and_evaluate`, which fetches every posting from the companies under `phase1` and scores the new ones. Ask for phase `all` (or `phase2`, `phase3`) to cover more.
4. **Scan without spending LLM calls** (optional). From a shell, `moonlighter-scan --no-eval` discovers and stores postings unscored, as `needs_review`; score one later with `verify_job`. See [Command line](../reference/cli.md).

```text
You: scan my companies

moonlighter: 3 sources scanned — 41 postings, 38 already known, 3 new
  ✓ NEW — Acme Robotics / Senior Backend Engineer
    Score: 8.1/10  (threshold: 6.5)
  ✓ NEW — Nimbus Health / Staff Engineer
    Score: 7.4/10
  ✗ Vandelay Industries / .NET Architect — 3.2/10, archived (hard filter: .NET)
```

The conversation is illustrative: Claude relays the tool's output in its own words. The tool itself reports how many jobs were processed, how many passed the threshold (with a table of them), and how many were filtered by title, archived for location, or scored below the threshold.

## How to read the scores

1. **Each score is 0–10**, from the LLM comparing the posting against your `profile.yaml`, including the hard and soft filters under `criteria`.
2. **Below the threshold, the job is archived automatically.** The threshold is `score_threshold` in `config.yaml`, 6.5 by default. A posting that breaks one of your hard filters (".NET" above) scores low and is archived with the reason.
3. **Some jobs are archived before any LLM call.** A title matching `title_blocklist` in `config.yaml` is saved as `archived` with a note, unscored. So is an onsite or hybrid posting outside the city you set as `criteria.home_city` in `profile.yaml`; without that key, nothing is archived by location. A remote posting, or one whose location doesn't settle the question, goes on to be scored.
4. **An empty description can't be scored.** Those jobs wait as `needs_review`: ask for `list_jobs` with status `needs_review`, open the posting, copy the whole page, and pass it to `verify_job` to score it.
5. **Browse what passed** with `list_jobs` (status `new` by default) and open one with `get_job` for its full details and history.

## How to prepare your first application

1. **Ask for the sheet.** "Prepare the application for the Acme one" runs `prepare_application`. Where the ATS API publishes the form's questions (Greenhouse, Recruitee), moonlighter reads them from there.
2. **No API? Paste the page.** When the questions aren't published, it asks you to open the application page, select all, copy, and hand the text over — that runs `prepare_application_from_paste`.
3. **Review the whole sheet.** Every question gets an answer drafted from your profile, or a flag saying why it needs you. This excerpt is in the tool's real format; the model is told to answer UNKNOWN when your profile gives it no basis, and that comes back as a gap:

   ```text
   [5/9] How many years have you run Elixir in production?  (required)
   !! I DON'T KNOW — no basis in your profile to answer

   1 of 9 need you
   ```

   Answer the flagged ones yourself, and read the drafted ones too — the model can still get an answer wrong.
4. **Paste and send it yourself.** Copy the answers into the employer's form and submit it there. moonlighter never opens the form and never clicks submit.
5. **Record that you sent it.** Tell Claude "mark job 42 as submitted" — that runs `update_status`. With [Gmail tracking](gmail.md) on, the sheet's email field already carries a tracking alias, and the recruiter's reply finds this application by itself.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
