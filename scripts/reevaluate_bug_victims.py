"""Re-avalia vagas que foram archivadas pelo bug do stdin (score_notes começa com
'evaluation error: claude CLI exited with code 1').

Usa eval_model do config (padrão: Haiku) para reduzir custo.
Aplica title_blocklist do config antes de chamar o LLM — custo zero.

Uso:
    python scripts/reevaluate_bug_victims.py [--dry-run] [--company SLUG] [--limit N] [--model MODEL] [--title-only] [--concurrency N]

Flags:
    --dry-run       Mostra o que seria feito, sem gravar no banco.
    --company       Filtra por empresa (ex: --company nubank).
    --limit         Processa no máximo N vagas (útil para testar).
    --model         Sobrescreve o eval_model do config.
    --title-only    Envia só o título pro LLM (sem a descrição completa). Muito mais barato.
    --concurrency N Quantas avaliações rodar em paralelo (padrão: 5).
                    Ao primeiro spend limit, para tudo imediatamente.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gauntler.core.config import load_config, load_profile
from gauntler.core.db import Job, init_db
from gauntler.core.llm import is_spend_limit, make_caller
from gauntler.core.log import setup as setup_logging
from gauntler.discovery.evaluator import evaluate_job, should_skip_by_title

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
                print(f"{label} -- skip título ({matched_pattern!r})")
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
                        print(f"{label} 🚫 COTA ATINGIDA — parando. Erro: {e}")
                    return
                async with print_lock:
                    print(f"{label} ✗ ERRO: {e}")
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
        print("\n🚫 Re-avaliação interrompida por spend limit.")

    llm_attempted = total - title_skipped
    mode = "título-only" if title_only else "descrição completa"
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Resultado: {total} vagas encontradas  [{mode}] concorrência={concurrency}")
    print(f"  -- ignoradas por título:   {title_skipped}")
    print(f"  ↑ promovidas para 'new':   {promoted}")
    print(f"     continuam archived:      {stayed_archived}")
    print(f"  ✗ erros:                   {errors}")
    print(f"  Chamadas LLM ({model}): {llm_attempted}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="Não grava no banco")
    parser.add_argument("--company", help="Filtra por empresa")
    parser.add_argument("--limit", type=int, help="Máximo de vagas a processar")
    parser.add_argument("--model", help="Sobrescreve eval_model do config")
    parser.add_argument(
        "--title-only",
        action="store_true",
        help="Usa só o título (sem descrição) — muito mais barato",
    )
    parser.add_argument(
        "--concurrency", type=int, default=5, help="Avaliações em paralelo (padrão: 5)"
    )
    args = parser.parse_args()

    setup_logging()
    config = load_config()
    profile = load_profile()
    init_db()  # resolve o path via gauntler_home() / GAUNTLER_DB_PATH (fonte única em db.py)

    model = args.model or config.get(
        "eval_model", config.get("llm_model", "claude-haiku-4-5-20251001")
    )

    victims = _fetch_victims(args.company, args.limit)
    if not victims:
        print("Nenhuma vaga com assinatura do bug encontrada.")
        return

    print(f"Vagas encontradas: {len(victims)}  |  modelo: {model}")
    by_company: dict[str, int] = {}
    for j in victims:
        by_company[j.company] = by_company.get(j.company, 0) + 1
    for company, count in sorted(by_company.items(), key=lambda x: -x[1]):
        print(f"  {company:20s}: {count}")

    if args.dry_run:
        print("\n⚠️  DRY RUN — nenhuma alteração será gravada.\n")

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
