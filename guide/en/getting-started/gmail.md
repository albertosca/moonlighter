🇺🇸 [English](gmail.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/getting-started/gmail/)

# Gmail tracking

Optional. When it is on, moonlighter reads recruiter replies from your Gmail inbox, matches each one to the application it answers by its tracking alias, and moves that application forward in the pipeline — so you know which applications got a reply without searching your inbox.

## How to connect Gmail

1. Create a project in [Google Cloud Console](https://console.cloud.google.com), enable the Gmail API, and download OAuth credentials as `client.json`.
2. Place the file at `gmail-client.json` inside `MOONLIGHTER_HOME` (default `~/.moonlighter/`).
3. Set `email.address` in `config.yaml` to the Gmail address you apply with. Each prepared sheet mints a tracking alias from it (`you+ref@gmail.com`), and that alias is how a reply finds its application.
4. The first call to `setup_email` opens a browser for authorization and saves the token.

From then on, ask Claude to run `sync_email_responses`, or run `moonlighter-email sync` from a shell or a cron job (see [Command line](../reference/cli.md)).

## What the sync reads and writes

- **Reads** your recent mail through the Gmail API, under your own OAuth credentials, going back `email.lookback_days` (default 30).
- **Classifies** each message with the LLM, in memory. Only a short generated summary is written to the local database — never the raw subject or body.
- **Matches** a reply to its application by the `+ref` alias, and only then advances that application. A reply without the alias is matched by company and title as a suggestion: it is reported to you, never applied.
- **Leaves Gmail untouched** by default: deduplication lives in a local table. Labelling and archiving are opt-in (`mark_processed`, `archive_ref_matched`, `archive_all_classified` — see [Configuration](../reference/config.md#email)) and need the `gmail.modify` scope.

[PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) lists everything the sync touches.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
