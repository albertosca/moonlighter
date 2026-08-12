"""Re-evaluates jobs archived by the stdin bug (score_notes starts with
'evaluation error: claude CLI exited with code 1').

Uses eval_model from config (default: Haiku) to reduce cost.
Applies title_blocklist from config before calling LLM — zero cost.

Usage:
    python scripts/reevaluate_bug_victims.py [--dry-run] [--company SLUG] [--limit N] [--model MODEL] [--title-only] [--concurrency N]

Flags:
    --dry-run       Shows what would be done without writing to the database.
    --company       Filter by company (ex: --company nubank).
    --limit         Process at most N jobs (useful for testing).
    --model         Override eval_model from config.
    --title-only    Send only the title to LLM (without full description). Much cheaper.
    --concurrency N How many evaluations to run in parallel (default: 5).
                    On first spend limit, stop everything immediately.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moonlighter.core.config import load_config, load_profile
from moonlighter.core.db import Job, init_db
from moonlighter.core.llm import is_spend_limit, make_caller
from moonlighter.core.log import setup as setup_logging
from moonlighter.core.metrics import operation_metrics
from moonlighter.discovery.evaluator import evaluate_job, should_skip_by_title

BUG_MARKER = "evaluation error: claude CLI exited with code 1"


def _fetch_victims(company: str | None, limit: int | None) -> list[Job]:
    query = Job.select().where(
        Job.score == 0,
        Job.status == "archived",
        Job.score_notes.startswith(BUG_MARKER),
    )
    if company:
        query = query.where(Job.company == company)
    query = query.order_by(Job.company, Job.id)
    if limit:
        query = query.limit(limit)
    return list(query)


async def _reevaluate(
    jobs: list[Job],
    config: dict,
    profile: dict,
    dry_run: bool,
    model: str,
    title_only: bool = False,
    concurrency: int = 5,
) -> None:
    with operation_metrics("reevaluate"):
        caller = make_caller(config)
        threshold = config.get("score_threshold", 6.5)
        blocklist: list[str] = config.get("title_blocklist", [])

        total = len(jobs)
        promoted = 0
        stayed_archived = 0
        title_skipped = 0
        errors = 0
        quota_hit = False

        sem = asyncio.Semaphore(concurrency)
        stop = asyncio.Event()
        print_lock = asyncio.Lock()

        async def _process(idx: int, job: Job) -> None:
            nonlocal promoted, stayed_archived, title_skipped, errors, quota_hit

            label = f"[{idx:4d}/{total}] [{job.company}] {job.title[:55]:55s}"

            matched_pattern = should_skip_by_title(job.title, blocklist)
            if matched_pattern:
                if not dry_run:
                    Job.update(
                        score=0.0,
                        score_notes=f"title filtered: {matched_pattern!r}",
                        caveats="[]",
                        status="archived",
                    ).where(Job.id == job.id).execute()
                async with print_lock:
                    print(f"{label} -- skip title ({matched_pattern!r})")
                    title_skipped += 1
                return

            if stop.is_set():
                return

            async with sem:
                if stop.is_set():
                    return

                try:
                    description = (
                        job.title
                        if title_only
                        else (job.description or f"{job.title} at {job.company}")
                    )
                    result = await evaluate_job(
                        company=job.company,
                        title=job.title,
                        description=description,
                        profile=profile,
                        model=model,
                        _caller=caller,
                    )
                except Exception as e:
                    if is_spend_limit(e):
                        stop.set()
                        quota_hit = True
                        async with print_lock:
                            print(f"{label} 🚫 SPEND LIMIT reached — stopping. Error: {e}")
                        return
                    async with print_lock:
                        print(f"{label} ✗ ERROR: {e}")
                        errors += 1
                    if not dry_run:
                        Job.update(score_notes=f"reevaluate_error: {str(e)[:200]}").where(
                            Job.id == job.id
                        ).execute()
                    return

                new_status = "new" if result.score >= threshold else "archived"
                icon = "↑ NEW" if new_status == "new" else "  arq"
                async with print_lock:
                    print(f"{label} {icon} score={result.score:.1f}")

                if not dry_run:
                    Job.update(
                        score=result.score,
                        score_notes=result.score_notes,
                        caveats=json.dumps(result.caveats),
                        salary_min=result.salary_min,
                        salary_max=result.salary_max,
                        salary_currency=result.salary_currency,
                        salary_source=result.salary_source,
                        status=new_status,
                    ).where(Job.id == job.id).execute()

                if new_status == "new":
                    promoted += 1
                else:
                    stayed_archived += 1

        await asyncio.gather(*[_process(idx, job) for idx, job in enumerate(jobs, 1)])

        if quota_hit:
            print("\n🚫 Re-evaluation interrupted by spend limit.")

        llm_attempted = total - title_skipped
        mode = "title-only" if title_only else "full description"
        prefix = "[DRY RUN] " if dry_run else ""
        print(f"\n{prefix}Result: {total} jobs found  [{mode}] concurrency={concurrency}")
        print(f"  -- skipped by title:       {title_skipped}")
        print(f"  ↑ promoted to 'new':       {promoted}")
        print(f"     remain archived:        {stayed_archived}")
        print(f"  ✗ errors:                  {errors}")
        print(f"  LLM calls ({model}):      {llm_attempted}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write to the database")
    parser.add_argument("--company", help="Filter by company")
    parser.add_argument("--limit", type=int, help="Maximum jobs to process")
    parser.add_argument("--model", help="Override eval_model from config")
    parser.add_argument(
        "--title-only",
        action="store_true",
        help="Use only the title (no description) — much cheaper",
    )
    parser.add_argument(
        "--concurrency", type=int, default=5, help="Evaluations in parallel (default: 5)"
    )
    args = parser.parse_args()

    setup_logging()
    config = load_config()
    profile = load_profile()
    init_db()  # resolve o path via moonlighter_home() / MOONLIGHTER_DB_PATH (fonte única em db.py)

    model = args.model or config.get(
        "eval_model", config.get("llm_model", "claude-haiku-4-5-20251001")
    )

    victims = _fetch_victims(args.company, args.limit)
    if not victims:
        print("No jobs with bug signature found.")
        return

    print(f"Jobs found: {len(victims)}  |  model: {model}")
    by_company: dict[str, int] = {}
    for j in victims:
        by_company[j.company] = by_company.get(j.company, 0) + 1
    for company, count in sorted(by_company.items(), key=lambda x: -x[1]):
        print(f"  {company:20s}: {count}")

    if args.dry_run:
        print("\n⚠️  DRY RUN — no changes will be saved.\n")

    asyncio.run(
        _reevaluate(
            victims,
            config,
            profile,
            dry_run=args.dry_run,
            model=model,
            title_only=args.title_only,
            concurrency=args.concurrency,
        )
    )


if __name__ == "__main__":
    main()
