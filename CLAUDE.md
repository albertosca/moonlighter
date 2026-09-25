# CLAUDE.md

Monorepo of 5 PEP 420 namespace packages under `packages/*/moonlighter/` — never add `__init__.py` at the `moonlighter/` namespace level.

`core` (config, db, llm, plugins) · `scan` (discovery: scanners, evaluator, staleness) · `apply` (assisted composer) · `email` (reply tracking) · `full` (the MCP server, `packages/full/moonlighter/server.py`). Entry points: `moonlighter` (MCP), `moonlighter-scan`, `moonlighter-apply`, `moonlighter-email` (JSON CLIs, one per slice).

Outside `packages/`: `guide/en|pt` (docs site source) · `scripts/` (CI checks, docs build, diagram render) · `assets/` (diagrams, social preview).

## Branches

`main` is protected: PR + 3 passing checks (`test`, `cla`, `security-audit`). A direct `git push` to main is rejected — branch, open a PR, `gh pr merge --auto --merge`.

`feat/ats-automation` holds the browser appliers deliberately removed from `main` in the assisted pivot (`37b1ac2`, 2026-08-12); that merge is not planned. Two traps: don't "restore" appliers to `main`, and don't plain-merge `main` into that branch — its tip was once an ancestor of `main`, so a fast-forward would have silently erased the code it exists to keep. A third trap: `DISCLAIMER.md` names this branch — renaming or deleting it stales that document; update both together.

## Commands

- Full suite: `uv run pytest -q` — the only green that counts; the 100% coverage gate needs the whole tree, so ANY subset run ends in `FAIL Required test coverage of 100% not reached`. That's an artifact of partial runs, not a regression: read the `N passed` line, then run the full suite before claiming green.
- `tests/test_performance.py::test_scan_log_dedup_1000_urls_fast` is timing-based and can fail under machine load; passing in isolation means flaky, not broken.
- After touching the lock: `uv sync --all-packages --all-extras`, the way `ci.yml` does. A plain `uv sync` prunes the `browser` extra, and `tests/core/test_browser.py` then dies with `ModuleNotFoundError: playwright` during collection — an incomplete install, not a regression.
- e2e tests are deselected by default (`addopts` carries `-m 'not e2e'`); run them with `uv run pytest -m e2e` — on `main` the only one needs `pdflatex` (browser e2e live on `feat/ats-automation`). A skipped e2e counts as a FAILURE (`tests/_e2e_guard.py`).
- Try a tool version before merging its Dependabot PR: `uvx ruff@0.16.3 format --check packages tests`.
- Lint: `uv run ruff check .` · Format: `uv run ruff format --check .`
- Types (mirror of ci.yml): `uv run mypy --package moonlighter.core --package moonlighter.discovery --package moonlighter.application --package moonlighter.tracking --package moonlighter.server --package moonlighter.startup --package moonlighter.views --package moonlighter._tool_logging --package moonlighter.init` — always `--package`, never file paths (paths duplicate module resolution in namespace packages). `scripts/` is not a package and gets its own line, `uv run mypy scripts/` — `ci.yml` runs both.
- Docs site: `bash scripts/build_docs.sh` builds `guide/en` + `guide/pt` into `site/` (Zensical, one build per language, then assembled — building both into one `site_dir` wipes a language). Preview one language live: `uv run --group docs zensical serve -f zensical.en.yml`. `--stamp` is CI-only (edits the working copy, refuses a shallow clone).
- README facts: `uv run pytest -q --junitxml=test-report.xml && uv run python scripts/check_readme_facts.py --junit test-report.xml` — fails when a written number is false or stale by more than 200 tests; update the facts blocks (both READMEs, both site homes, llms.txt) and `assets/site/social-preview.svg` + its PNG together.
- Zensical is pre-1.0: build a Dependabot bump locally (`uv run --group docs --with zensical==X zensical build --strict -f zensical.en.yml`) before merging it.
- After a social-preview PNG change, re-upload it in GitHub Settings → Social preview (UI only); verify with `curl -s https://github.com/albertosca/moonlighter | grep og:image`.
- Diagrams: edit `assets/diagrams/src/*.svg` ({{fg}}/{{muted}}/{{accent}}/{{ground}}), then `uv run python scripts/render_diagrams.py` — never hand-edit the generated `*-light.svg`/`*-dark.svg`.
- CI pins uv to the version that writes the lock locally (0.12.19 since 2026-09-25) and keeps `actions/setup-python` 3.14 before `setup-uv`: the old 0.7.6 pin, alone, picked cpython-3.14.0a7 and Zensical crashed. `setup-uv` has no floating major tags since v8 — pin an exact tag.
- Zensical strips accents from heading anchors, GitHub keeps them: README links into the site are absolute site URLs, checked with their `#anchors` by `scripts/check_built_site.py`.
- `.gitignore` anchors `/site/` on purpose — unanchored `site/` also ignores `assets/site/`.
- Public copy (READMEs, guide/, plugin and package descriptions): banned claims and the approved headline live in `docs/superpowers/product-marketing.md` — read it first.

## Quick DB access

`uv run python -c "from moonlighter.core.db import init_db, Job, Application; init_db(); ..."` — peewee models against the DB under `MOONLIGHTER_HOME` (default `~/.moonlighter`).

Peewee's metaclass-injected attrs (`.id`, `.DoesNotExist`, `.get_or_create`) are declared once on `BaseModel` in `core/db.py`. peewee ships stubs since 4.2, so mypy sees a real class and these stopped being implicit — fix at that shared base, never with per-call-site `type: ignore`.

## Docs

`docs/superpowers/` is a **symlink** to `~/Programming/private-project-docs/moonlighter` (a separate private repo). Git run from inside moonlighter sees nothing there: it answers `beyond a symbolic link` and exits non-zero, which reads as "untracked" — and leads to the wrong conclusion that specs, plans and dossiers can't be recovered. They can. Commit those changes from inside `~/Programming/private-project-docs`.

## Releases

Versions move in lockstep BY HAND: bump all five `pyproject.toml` AND the four `==` pins in `moonlighter-full` together. `scripts/check_version_lockstep.py` runs as the CI `test` job's first step and fails fast (before installing anything) if any of the five drift from each other.
