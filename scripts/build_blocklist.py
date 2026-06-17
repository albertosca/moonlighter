"""Analisa vagas com score baixo e propõe padrões de blocklist validados por IA.

Fluxo:
  1. Busca vagas archived com 0 < score <= threshold (avaliadas de verdade)
  2. Agrupa títulos por empresa
  3. Para cada empresa, pede ao LLM: "proponha substrings seguras para bloquear"
  4. LLM retorna padrões com reasoning e flag safe=true/false
  5. Padrões aprovados (safe=true) vão para blocklist_learned.yaml
  6. load_config() já mescla o arquivo ao title_blocklist

Uso:
    python scripts/build_blocklist.py [--threshold 3.0] [--dry-run] [--company SLUG]

Flags:
    --threshold  Score máximo para considerar uma vaga como candidata (padrão: 3.0)
    --dry-run    Mostra o que seria adicionado sem gravar no arquivo
    --company    Processa só uma empresa
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from candidatador.config import load_config
from candidatador.db import Job, init_db
from candidatador.llm import make_caller
from candidatador.log import setup as setup_logging
from candidatador.parsing import _extract_json

LEARNED_PATH = _ROOT / "blocklist_learned.yaml"

PROPOSAL_PROMPT = """\
You are building a job title blocklist for Alberto, a senior software engineer (15+ years, \
Staff-level, Elixir/Ruby/Python/JS). He is looking for engineering roles only.

The following job titles at **{company}** were evaluated and scored {threshold} or below out of 10 \
— meaning they are clearly irrelevant for him:

{titles}

Your task: propose minimal, safe **substring patterns** (lowercase) to block future titles like these \
before they reach the LLM evaluator.

A pattern is SAFE only if you are confident that **every possible job title containing it** would be \
irrelevant for a senior software engineer. When in doubt, mark safe=false.

Examples of UNSAFE patterns (too broad):
- "analista" alone → "analista de segurança" could be relevant
- "gerente" alone → "Engineering Manager" might appear in PT-BR as "Gerente de Engenharia"
- "especialista" alone → "Especialista de Plataforma" could be a tech role

Examples of SAFE patterns:
- "gerente de relacionamento" → always a banking relationship manager, never engineering
- "banco de talentos" → always a talent pool post, not a real opening
- "estagiár" → always an intern position

Return a JSON array (no markdown):
[
  {{
    "pattern": "lowercase substring to match",
    "examples": ["example title 1", "example title 2"],
    "safe": true,
    "reasoning": "one sentence explaining why all matching titles would be irrelevant"
  }}
]

Return [] if no safe patterns can be identified.\
"""

QUOTA_MARKERS = (
    "spend limit",
    "quota",
    "rate limit",
    "too many requests",
    "overloaded",
    "429",
    "usage limit",
)


def _load_learned() -> list[str]:
    if not LEARNED_PATH.exists():
        return []
    data = yaml.safe_load(LEARNED_PATH.read_text()) or {}
    return data.get("title_blocklist", [])


def _save_learned(patterns: list[str]) -> None:
    existing = _load_learned()
    merged = list(dict.fromkeys(existing + patterns))  # dedup, preserve order
    LEARNED_PATH.write_text(
        yaml.dump({"title_blocklist": merged}, allow_unicode=True, default_flow_style=False)
    )


def _fetch_low_scorers(threshold: float, company: str | None) -> dict[str, list[str]]:
    """Returns {company: [title, ...]} for archived jobs with 0 < score <= threshold."""
    query = (
        Job.select(Job.company, Job.title)
        .where(
            Job.score > 0,
            Job.score <= threshold,
            Job.status == "archived",
            Job.score_notes.is_null(False),
            ~Job.score_notes.startswith("evaluation error"),
            ~Job.score_notes.startswith("title filtered"),
            ~Job.score_notes.startswith("reevaluate_error"),
        )
        .order_by(Job.company, Job.title)
    )
    if company:
        query = query.where(Job.company == company)

    grouped: dict[str, list[str]] = {}
    for job in query:
        grouped.setdefault(job.company, []).append(job.title)
    return grouped


async def _propose_for_company(
    company: str, titles: list[str], threshold: float, caller, model: str
) -> list[dict]:
    titles_block = "\n".join(f"- {t}" for t in titles[:80])  # cap at 80 to avoid huge context
    prompt = PROPOSAL_PROMPT.format(
        company=company,
        threshold=threshold,
        titles=titles_block,
    )
    try:
        raw = await caller(prompt, model)
        extracted = _extract_json(raw)
        proposals = json.loads(extracted)
        if not isinstance(proposals, list):
            return []
        return [
            p
            for p in proposals
            if isinstance(p, dict) and p.get("safe") is True and p.get("pattern")
        ]
    except Exception as e:
        err = str(e).lower()
        if any(m in err for m in QUOTA_MARKERS):
            raise
        print(f"  ⚠️  Erro ao processar {company}: {e}")
        return []


async def _run(
    threshold: float, company_filter: str | None, dry_run: bool, model: str, config: dict
) -> None:
    caller = make_caller(config)
    grouped = _fetch_low_scorers(threshold, company_filter)

    if not grouped:
        print("Nenhuma vaga encontrada com os critérios.")
        return

    total_titles = sum(len(v) for v in grouped.values())
    print(
        f"Vagas para análise: {total_titles} em {len(grouped)} empresa(s)  [threshold={threshold}]"
    )
    print()

    existing = set(_load_learned())
    all_new: list[str] = []

    for company, titles in sorted(grouped.items(), key=lambda x: -len(x[1])):
        print(f"▶ {company} ({len(titles)} vagas)...")
        try:
            proposals = await _propose_for_company(company, titles, threshold, caller, model)
        except Exception as e:
            if any(m in str(e).lower() for m in QUOTA_MARKERS):
                print(f"🚫 COTA ATINGIDA — parando. Erro: {e}")
                break
            print(f"  ✗ Erro: {e}")
            continue

        if not proposals:
            print("  (nenhum padrão seguro identificado)")
            continue

        for p in proposals:
            pattern = p["pattern"].lower().strip()
            status = (
                "JÁ EXISTE" if pattern in existing else ("DRY RUN" if dry_run else "ADICIONADO")
            )
            print(f"  + {pattern!r:40s} [{status}]")
            print(f"    → {p.get('reasoning', '')}")
            if pattern not in existing and not dry_run:
                all_new.append(pattern)
                existing.add(pattern)
        print()

    if all_new and not dry_run:
        _save_learned(all_new)
        print(f"✓ {len(all_new)} padrão(ões) gravado(s) em blocklist_learned.yaml")
    elif dry_run and all_new:
        print(f"[DRY RUN] {len(all_new)} padrão(ões) seriam adicionados.")
    else:
        print("Nenhum padrão novo.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--threshold", type=float, default=3.0, help="Score máximo para considerar (padrão: 3.0)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Não grava no arquivo")
    parser.add_argument("--company", help="Processa só uma empresa")
    args = parser.parse_args()

    setup_logging()
    config = load_config()
    db_path = str(Path(config.get("db_path", "~/.candidatador/candidatador.db")).expanduser())
    os.environ["CANDIDATADOR_DB"] = db_path
    init_db()

    model = config.get("eval_model", "claude-haiku-4-5-20251001")
    print(f"Modelo: {model}  |  blocklist_learned.yaml: {LEARNED_PATH}")
    print()

    asyncio.run(_run(args.threshold, args.company, args.dry_run, model, config))


if __name__ == "__main__":
    main()
