"""Default values for config.yaml, merged under the user's settings at load time."""

from typing import Any

DEFAULTS: dict[str, Any] = {
    # Browser executable path (Chrome/Chromium/Brave). Empty by default:
    # set browser_path in config.yaml. Accepts brave_path (legacy) as a fallback.
    "browser_path": "",
    # Which LLM backend runs evaluations and answer generation.
    #   "cli" -> the `claude` CLI, using the claude.ai subscription. No API key.
    #   "api" -> the Anthropic SDK. Requires ANTHROPIC_API_KEY.
    #   "cursor" -> the Cursor `agent` CLI (`cursor-agent` if `agent` is absent).
    #               Account login (`agent login`). llm_model is not forwarded:
    #               those ids belong to Anthropic and the Cursor CLI rejects them.
    #               Optional `cursor_model` is forwarded as `--model` when set.
    #   "codex" -> the OpenAI `codex` CLI on a ChatGPT login (`codex login`); an API
    #              key is refused. Unlike cursor it forwards llm_model / eval_model
    #              as `--model`, so both must name a non-Claude model (eval_model
    #              defaults to llm_model when omitted).
    # Default is "cli" because that is what `moonlighter init`, the README, and
    # config.example.yaml all lead with -- an installer coming through
    # `uvx moonlighter` has Claude Code far more often than an API key.
    "llm_backend": "cli",
    # Seconds a `claude -p` call may run before it is killed and fails. One call
    # hung for the whole 300 s of a test harness on 2026-09-25 with nothing to end it.
    "llm_timeout_seconds": 180,
    "score_threshold": 6.5,
    # A banked answer older than this (days since it was last promoted, i.e.
    # last submitted somewhere) is not replayed. "When can you start?" is the
    # concrete case: true for a while, then quietly wrong. null disables expiry.
    "answer_bank_max_age_days": 90,
    "llm_model": "claude-sonnet-4-6",
    "eval_model": "claude-haiku-4-5-20251001",
    "slow_mo_ms": 300,
    "title_blocklist": [],
    # Max parallel LLM evaluations in the scan. Bounds the token burst and the
    # waste after the spend-limit (in-flight siblings). With batching (scan_batch_size),
    # this is the number of BATCHES in parallel. Effective concurrency = scan_concurrency × scan_batch_size.
    "scan_concurrency": 5,
    # Jobs evaluated per LLM call. The profile is sent once per batch, cutting
    # re-transmission by a factor of K. 1 disables batching (1 job per call).
    "scan_batch_size": 5,
    # CV per company. Paths relative to MOONLIGHTER_HOME; case-insensitive match.
    # 'default' used when the company has no entry, and defaults to 'cv.pdf'
    # (i.e. MOONLIGHTER_HOME/cv.pdf) — the same file the startup warning names.
    # Can be overridden in the local config.yaml. If the chosen file doesn't
    # exist, the composer emits a gap on the file-upload question instead of
    # naming a file to attach.
    "cv": {
        "default": "cv.pdf",
        "by_company": {},
    },
    # Country-dependent work authorization. The candidate is authorized to work
    # only in their citizenship country. When the job's country cannot be
    # confidently inferred, the field becomes __NEEDS_REVIEW__ (manual decision — never a guess).
    "work_authorization": {
        "citizenship_country": "",
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
    },
    # Gmail response tracking. Relative filenames, resolved under MOONLIGHTER_HOME
    # by resolve_under_home() at the point of use (same convention as cv.default) —
    # NOT hardcoded to ~/.moonlighter, which ignores a MOONLIGHTER_HOME override.
    # setup_email() creates the token after the OAuth consent. NOTE: setup_email()
    # writes (and overwrites) whatever file token_path names — point it at an
    # absolute path elsewhere only if you own that file.
    "email": {
        "credentials_path": "gmail-client.json",
        "token_path": "gmail-token.json",
    },
    # Portal-feed jobs (RemoteOK, HN Who Is Hiring, ...) can never be
    # staleness-checked at their source; past this age they archive as aged
    # out. 0 disables age-based archiving.
    "portal_max_age_days": 30,
}
