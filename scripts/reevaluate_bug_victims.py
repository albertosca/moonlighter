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
"""  # noqa: D205 - argparse prints this docstring verbatim as the --help description

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reevaluation_batch import ReevaluationSettings, reevaluate

from moonlighter.core.config.loading import load_config, load_profile
from moonlighter.core.db import Job, init_db
from moonlighter.core.log import setup as setup_logging

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
    arguments = parser.parse_args()

    setup_logging()
    config = load_config()
    profile = load_profile()
    init_db()  # resolves the path via moonlighter_home() / MOONLIGHTER_DB_PATH (single source in db.py)

    model = arguments.model or config.get(
        "eval_model", config.get("llm_model", "claude-haiku-4-5-20251001")
    )

    victims = _fetch_victims(arguments.company, arguments.limit)
    if not victims:
        print("No jobs with bug signature found.")
        return

    print(f"Jobs found: {len(victims)}  |  model: {model}")
    by_company: dict[str, int] = {}
    for victim in victims:
        by_company[victim.company] = by_company.get(victim.company, 0) + 1
    for company, count in sorted(by_company.items(), key=lambda item: -item[1]):
        print(f"  {company:20s}: {count}")

    if arguments.dry_run:
        print("\n⚠️  DRY RUN — no changes will be saved.\n")

    settings = ReevaluationSettings(
        model=model,
        profile=profile,
        threshold=config.get("score_threshold", 6.5),
        title_blocklist=config.get("title_blocklist", []),
        dry_run=arguments.dry_run,
        title_only=arguments.title_only,
        concurrency=arguments.concurrency,
    )
    asyncio.run(reevaluate(victims, config, settings))


if __name__ == "__main__":
    main()
