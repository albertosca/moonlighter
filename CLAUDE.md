# CLAUDE.md

Monorepo of 5 PEP 420 namespace packages under `packages/*/moonlighter/` — never add `__init__.py` at the `moonlighter/` namespace level.

`core` (config, db, llm, plugins) · `scan` (discovery: scanners, evaluator, staleness) · `apply` (assisted composer) · `email` (reply tracking) · `full` (the MCP server, `packages/full/moonlighter/server.py` — the only entry point).

## Branches

`main` is protected: PR + 3 passing checks (`test`, `cla`, `security-audit`). A direct `git push` to main is rejected — branch, open a PR, `gh pr merge --auto --merge`.

`feat/ats-automation` holds the browser appliers deliberately removed from `main` in the assisted pivot (`37b1ac2`, 2026-08-12); that merge is not planned. Two traps: don't "restore" appliers to `main`, and don't plain-merge `main` into that branch — its tip was once an ancestor of `main`, so a fast-forward would have silently erased the code it exists to keep. A third trap: `DISCLAIMER.md` names this branch — renaming or deleting it stales that document; update both together.

## Commands

- Full suite: `uv run pytest -q` — the only green that counts; the 100% coverage gate needs the whole tree, so ANY subset run ends in `FAIL Required test coverage of 100% not reached`. That's an artifact of partial runs, not a regression: read the `N passed` line, then run the full suite before claiming green.
- `tests/test_performance.py::test_scan_log_dedup_1000_urls_fast` is timing-based and can fail under machine load; passing in isolation means flaky, not broken.
- After touching the lock: `uv sync --all-packages --all-extras`, the way `ci.yml` does. A plain `uv sync` prunes the `browser` extra, and `tests/core/test_browser.py` then dies with `ModuleNotFoundError: playwright` during collection — an incomplete install, not a regression.
- e2e tests are deselected by default (`addopts` carries `-m 'not e2e'`); run them with `uv run pytest -m e2e` — they need a real browser.
- Try a tool version before merging its Dependabot PR: `uvx ruff@0.16.3 format --check packages tests`.
- Lint: `uv run ruff check .` · Format: `uv run ruff format --check .`
- Types (mirror of ci.yml): `uv run mypy --package moonlighter.core --package moonlighter.discovery --package moonlighter.application --package moonlighter.tracking --package moonlighter.server --package moonlighter.startup --package moonlighter.views --package moonlighter._tool_logging --package moonlighter.init` — always `--package`, never file paths (paths duplicate module resolution in namespace packages).

## Quick DB access

`uv run python -c "from moonlighter.core.db import init_db, Job, Application; init_db(); ..."` — peewee models against the DB under `MOONLIGHTER_HOME` (default `~/.moonlighter`).

Peewee's metaclass-injected attrs (`.id`, `.DoesNotExist`, `.get_or_create`) are declared once on `BaseModel` in `core/db.py`. peewee ships stubs since 4.2, so mypy sees a real class and these stopped being implicit — fix at that shared base, never with per-call-site `type: ignore`.

## Docs

`docs/superpowers/` is a **symlink** to `~/Programming/private-project-docs/moonlighter` (a separate private repo). Git run from inside moonlighter sees nothing there: it answers `beyond a symbolic link` and exits non-zero, which reads as "untracked" — and leads to the wrong conclusion that specs, plans and dossiers can't be recovered. They can. Commit those changes from inside `~/Programming/private-project-docs`.

## Releases

Versions move in lockstep BY HAND: bump all five `pyproject.toml` AND the four `==` pins in `moonlighter-full` together. `scripts/check_version_lockstep.py` runs as the CI `test` job's first step and fails fast (before installing anything) if any of the five drift from each other.
