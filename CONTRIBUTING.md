# Contributing to moonlighter

Thanks for your interest. This document covers how to get set up, what the quality bar is, and
the one legal step required before a pull request can be merged.

## Contributor License Agreement

Every pull request requires a signed [CLA](CLA.md). This is automated: open a PR and a bot will
comment with instructions. Signing is a one-time comment on your first PR.

**Why a CLA and not just the AGPL?** The project is AGPL-3.0 and will stay that way. The CLA
grants the maintainer the additional right to offer a commercially licensed version. Without it,
that option would be permanently foreclosed once contributions land.

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
uv run mypy --package moonlighter.core --package moonlighter.discovery \
            --package moonlighter.application --package moonlighter.tracking \
            --package moonlighter.server
```

Tests are written first. Coverage is gated at 100% — use `# pragma: no cover` only for
genuinely unreachable defensive branches, never to skip a real path.

## Adding a new ATS

Pull requests adding a scanner or applier to this repository are welcome — open one and we'll
review it like any other change.

You also have the option not to. moonlighter discovers scanners and appliers through
`entry_points`, so you can ship one as a separate package without touching this repo at all, and
keep it on your own release schedule under whatever license you like. See the "Extending
moonlighter" section of the [README](README.md).

Both paths are supported. Pick whichever fits how you want to maintain it.

## Reporting security issues

Do not open a public issue. Email the maintainer directly.
