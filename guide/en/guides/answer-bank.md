🇺🇸 [English](answer-bank.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/guides/answer-bank/)

# Answer bank

The answer bank keeps the screening answers you approved, so a question you already answered on one application is answered the same way on the next — without another LLM call.

## How answers are reused

Every non-choice screening answer you approve — "years of Elixir", "notice period", anything an application form asks that isn't a static profile field — is cached per job and also promoted to a cross-job bank, so a question worded the same way on a later application reuses the answer instead of asking the LLM again.

An answer is promoted when you mark its application as sent (`update_status` with `submitted`), or when `sync_email_responses` sees a reply advance that application. Both happen in the MCP server; the standalone `moonlighter-email sync` command does not feed the bank (see [Command line](../reference/cli.md)).

## When a banked answer expires

A banked answer expires after `answer_bank_max_age_days` (default 90; `null` disables expiry — see [Configuration](../reference/config.md)) counted from the last time it was submitted, so a notice-period or availability answer that goes stale gets asked again instead of replayed forever.

## How to inspect and forget answers

`list_answer_bank` shows what's cached, most recently used first, with expired entries marked. `forget_answer` deletes one, so the next application asks fresh.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
