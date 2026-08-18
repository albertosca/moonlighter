# CLAUDE.md

Monorepo of 5 PEP 420 namespace packages under `packages/*/moonlighter/` — never add `__init__.py` at the `moonlighter/` namespace level.

## Commands

- Full suite: `uv run pytest -q` — the only green that counts; the 100% coverage gate needs the whole tree, so ANY subset run ends in `FAIL Required test coverage of 100% not reached`. That's an artifact of partial runs, not a regression: read the `N passed` line, then run the full suite before claiming green.
- `tests/test_performance.py::test_scan_log_dedup_1000_urls_fast` is timing-based and can fail under machine load; passing in isolation means flaky, not broken.
- Lint: `uv run ruff check .` · Format: `uv run ruff format --check .`
- Types (mirror of ci.yml): `uv run mypy --package moonlighter.core --package moonlighter.discovery --package moonlighter.application --package moonlighter.tracking --package moonlighter.server --package moonlighter.startup --package moonlighter.views --package moonlighter._tool_logging --package moonlighter.init` — always `--package`, never file paths (paths duplicate module resolution in namespace packages).

## Quick DB access

`uv run python -c "from moonlighter.core.db import init_db, Job, Application; init_db(); ..."` — peewee models against the DB under `MOONLIGHTER_HOME` (default `~/.moonlighter`).

## Releases

Versions move in lockstep BY HAND: bump all five `pyproject.toml` AND the four `==` pins in `moonlighter-full` together — nothing in CI checks this.
