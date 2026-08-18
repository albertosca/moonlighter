# Contributing to moonlighter

Thanks for your interest. This document covers how to get set up, what the quality bar is, and
the one legal step required before a pull request can be merged.

## Contributor License Agreement

Every pull request requires a signed [CLA](CLA.md). This is automated: open a PR and a bot will
comment with instructions. Signing is a one-time comment on your first PR.

`main` only accepts pull requests, and three checks must be green before the merge button works:
`cla`, `test`, and `security-audit`.

**Why a CLA and not just the AGPL?** The public project remains AGPL-3.0. The CLA additionally
lets the maintainer offer a separately licensed commercial version built on top of contributions.

## Development setup

```bash
git clone https://github.com/albertosca/moonlighter
cd moonlighter
uv sync --all-packages
```

## Quality bar

Every change must pass all three before review:

```bash
uv run pytest                    # 100% branch coverage is enforced
uv run ruff check . && uv run ruff format --check .
uv run mypy \
  --package moonlighter.core \
  --package moonlighter.discovery \
  --package moonlighter.application \
  --package moonlighter.tracking \
  --package moonlighter.server \
  --package moonlighter.startup \
  --package moonlighter.views \
  --package moonlighter._tool_logging \
  --package moonlighter.init
```

Tests are written first. Coverage is gated at 100% — use `# pragma: no cover` only for
genuinely unreachable defensive branches, never to skip a real path.

## Adding a new ATS

Pull requests adding a scanner or a form-schema source to this repository are welcome — open one
and we'll review it like any other change.

You also have the option not to. moonlighter discovers scanners through
`entry_points`, so you can ship one as a separate package without touching this repo at all, and
keep it on your own release schedule under whatever license you like. See the "Extensions (adding
a new ATS)" section of the [README](README.md).

Both paths are supported. Pick whichever fits how you want to maintain it.

## Reporting security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md) for how to report a vulnerability.
