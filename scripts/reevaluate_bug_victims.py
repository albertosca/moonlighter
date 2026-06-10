"""Re-avalia vagas que foram archivadas pelo bug do stdin (score_notes começa com
'evaluation error: claude CLI exited with code 1').

Uso:
    python scripts/reevaluate_bug_victims.py [--dry-run] [--company SLUG] [--limit N]

Flags:
    --dry-run     Mostra o que seria feito, sem gravar no banco.
    --company     Filtra por empresa (ex: --company nubank).
    --limit       Processa no máximo N vagas (útil para testar).
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from candidatador.config import load_config, load_profile
from candidatador.db import Job, init_db
from candidatador.evaluator import evaluate_job
from candidatador.llm import make_caller
from candidatador.log import setup as setup_logging

BUG_MARKER = "evaluation error: claude CLI exited with code 1"
BATCH_SIZE = 1  # serial: o CLI claude não suporta múltiplas instâncias concorrentes


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


async def _reevaluate(jobs: list[Job], config: dict, profile: dict, dry_run: bool) -> None:
    caller = make_caller(config)
    model = config.get("llm_model", "claude-sonnet-4-6")
    threshold = config.get("score_threshold", 6.5)

    total = len(jobs)
    promoted = 0
    stayed_archived = 0
    errors = 0

    for idx, job in enumerate(jobs, 1):
        print(f"[{idx:4d}/{total}] [{job.company}] {job.title[:55]:55s}", end=" ", flush=True)

        try:
            result = await evaluate_job(
                company=job.company,
                title=job.title,
                description=job.description or f"{job.title} at {job.company}",
                profile=profile,
                model=model,
                _caller=caller,
            )
        except Exception as e:
            print(f"✗ ERRO: {e}")
            errors += 1
            continue

        new_status = "new" if result.score >= threshold else "archived"
        icon = "↑ NEW" if new_status == "new" else "  arq"
        print(f"{icon} score={result.score:.1f}")

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

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Resultado: {total} vagas processadas")
    print(f"  ↑ promovidas para 'new':  {promoted}")
    print(f"    continuam archived:      {stayed_archived}")
    print(f"  ✗ erros:                  {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Não grava no banco")
    parser.add_argument("--company", help="Filtra por empresa")
    parser.add_argument("--limit", type=int, help="Máximo de vagas a processar")
    args = parser.parse_args()

    setup_logging()
    config = load_config()
    profile = load_profile()
    db_path = os.path.expanduser(config.get("db_path", "~/.candidatador/candidatador.db"))
    os.environ["CANDIDATADOR_DB"] = db_path
    init_db()

    victims = _fetch_victims(args.company, args.limit)
    if not victims:
        print("Nenhuma vaga com assinatura do bug encontrada.")
        return

    print(f"Vagas a reavaliar: {len(victims)}")
    by_company: dict[str, int] = {}
    for j in victims:
        by_company[j.company] = by_company.get(j.company, 0) + 1
    for company, count in sorted(by_company.items(), key=lambda x: -x[1]):
        print(f"  {company:20s}: {count}")

    if args.dry_run:
        print("\n⚠️  DRY RUN — nenhuma alteração será gravada.\n")

    asyncio.run(_reevaluate(victims, config, profile, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
