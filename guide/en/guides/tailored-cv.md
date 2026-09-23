🇺🇸 [English](tailored-cv.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/guides/tailored-cv/)

# Tailored CV per job

Optional. With a curated bullet pool in place, `prepare_application` also produces a one-page PDF of your CV tailored to the posting, built from bullets you wrote and rendered through your own LaTeX template.

## How the tailored CV is built

When a curated bullet pool exists — `cv-pool.yaml` in `MOONLIGHTER_HOME`, or wherever `cv.pool` in `config.yaml` points — `prepare_application` also tailors your CV to the posting: one LLM call selects and orders bullets from your pool and writes a short summary from your profile (it can also answer "the base CV already fits" and change nothing), and the result renders through your own LaTeX template and compiles with `pdflatex` when installed.

- **Always one page.** The prompt carries the budget, and the orchestrator drops the least relevant bullets until pdflatex reports a single page.
- **Always plain Latin text.** A model field carrying an emoji, symbol or non-Latin script is replaced whole by your curated text, never edited.
- **Grouped roles.** Consecutive roles at the same company render as one grouped block with the overall date span, instead of two separate entries.
- **Your bullets, not the model's.** Every bullet comes from your pool; the model chooses and orders them (translating them for a Portuguese posting), and writes the summary under instructions to use only your profile and never inflate a claim. The sheet always tells you to review the generated PDF before uploading.

Without a pool file no CV is generated and no extra LLM call is made — but `prepare_application` does offer to draft you one, returning that offer instead of a sheet, until you either bootstrap a pool or skip it (see [Starting a pool](#starting-a-pool)).

## Configuration and cache

Config keys: `cv.pool`, `cv.template_dir` (holding `cv-template.en.tex`, optionally `cv-template.pt.tex` for Portuguese postings), `cv.generated_dir` (default `~/.moonlighter/cv-generated`). Defaults for each are in [Configuration](../reference/config.md#cv).

Each job's result is cached under `<generated_dir>/<job_id>/`, so no job is ever generated twice — after editing your pool or template, delete that directory to have the next `prepare_application` regenerate that job's CV.

## Starting a pool

No `cv.pool` yet? `prepare_application` offers to draft one from your `profile.yaml` whenever it's missing (or run `moonlighter-apply bootstrap-cv` from a shell) — a first draft you review and edit. It is built from the generic [example pool](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/cvgen/templates/cv-pool.example.yaml) and [example template](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/cvgen/templates/cv-template.en.example.tex), which double as the schema reference if you'd rather hand-write a pool instead. Both ship inside the installed package too, under `moonlighter/application/cvgen/templates/`, so a checkout is not required to read them.

In Claude, `bootstrap_cv_pool` drafts the pool and `skip_cv_bootstrap` declines the offer for good (see [MCP tools](../reference/mcp-tools.md)).

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
