🇺🇸 [English](tailored-cv.md) · 🇧🇷 [Português](https://albertosca.github.io/moonlighter/pt/guides/tailored-cv/)

# Tailored CV per job

### Tailored CV per job (optional)

When `cv.pool` in `config.yaml` points at a curated bullet pool (`cv-pool.yaml`), `prepare_application` also tailors your CV to the posting: one LLM call selects and orders bullets from your pool (it can also answer "the base CV already fits" and change nothing), the result renders through your own LaTeX template and compiles with `pdflatex` when installed. The result is always one page (the prompt carries the budget, and the orchestrator drops the least relevant bullets until pdflatex reports a single page) and plain Latin text: a model field carrying an emoji, symbol or non-Latin script is replaced whole by your curated text, never edited. Consecutive roles at the same company render as one grouped block with the overall date span, instead of two separate entries. The model never authors a factual claim — it only selects from what you curated — and the sheet always tells you to review the generated PDF before uploading. Without a pool file no CV is generated and no extra LLM call is made — but `prepare_application` does offer to draft you one, returning that offer instead of a sheet, until you either bootstrap a pool or skip it (see below).

Config keys: `cv.pool`, `cv.template_dir` (holding `cv-template.en.tex`, optionally `cv-template.pt.tex` for Portuguese postings), `cv.generated_dir` (default `~/.moonlighter/cv-generated`).

Each job's result is cached under `<generated_dir>/<job_id>/`, so no job is ever generated twice — after editing your pool or template, delete that directory to have the next `prepare_application` regenerate that job's CV.

No `cv.pool` yet? `prepare_application` offers to draft one from your `profile.yaml` whenever it's missing (or run `moonlighter-apply bootstrap-cv` from a shell) — a first draft you review and edit. It is built from the generic [example pool](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/cvgen/templates/cv-pool.example.yaml) and [example template](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/cvgen/templates/cv-template.en.example.tex), which double as the schema reference if you'd rather hand-write a pool instead. Both ship inside the installed package too, under `moonlighter/application/cvgen/templates/`, so a checkout is not required to read them.

[← Back to the README](https://github.com/albertosca/moonlighter#readme)
