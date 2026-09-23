🇺🇸 [English](answer-bank.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/guides/answer-bank/)

# Answer bank

### Answer bank

Every non-choice screening answer you approve — "years of Elixir", "notice period", anything an
application form asks that isn't a static profile field — is cached per job and also promoted to a
cross-job bank, so a question worded the same way on a later application reuses the answer instead of
asking the LLM again. A banked answer expires after `answer_bank_max_age_days` (default 90,
`config.example.yaml`; `null` disables expiry) counted from the last time it was submitted, so a
notice-period or availability answer that goes stale gets asked again instead of replayed forever.
`list_answer_bank` shows what's cached (expired entries marked); `forget_answer` deletes one so the next
application asks fresh.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
