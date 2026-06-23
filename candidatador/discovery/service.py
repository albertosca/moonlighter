"""Serviço de scan: descobre vagas (HTTP + LinkedIn), avalia com LLM e salva.

As tools MCP em server.py são wrappers finos que chamam estas funções passando
config/profile/caller. A lógica fica aqui, testável isolada.
"""

import asyncio
import json
import re
from typing import Any

import httpx
from peewee import IntegrityError

from candidatador.core import browser
from candidatador.core.config import load_company_list
from candidatador.core.db import Job, ScanLog
from candidatador.core.llm import LLMCaller
from candidatador.core.log import get_logger
from candidatador.discovery.evaluator import evaluate_job, should_skip_by_title
from candidatador.discovery.sources.base import RawJob
from candidatador.discovery.sources.http import AshbyScanner, GreenhouseScanner, LeverScanner
from candidatador.views import render_jobs_table

logger = get_logger(__name__)

_SPEND_LIMIT_MARKERS = (
    "spend limit",
    "quota",
    "rate limit",
    "too many requests",
    "overloaded",
    "429",
    "usage limit",
)

BATCH_SIZE = 10


def _is_spend_limit(exc: Exception) -> bool:
    """True se a exceção indica esgotamento de cota/limite de gasto do LLM."""
    msg = str(exc).lower()
    return any(m in msg for m in _SPEND_LIMIT_MARKERS)


class _StopScan:
    """Sentinela devolvida por uma coroutine que detectou spend limit e parou."""


def _model_for(config: dict[str, Any]) -> str:
    model: str = config.get("eval_model", config.get("llm_model", "claude-haiku-4-5-20251001"))
    return model


def _claim(raw: RawJob) -> bool:
    """Reserva a URL no ScanLog antes de qualquer trabalho. ScanLog.create é
    síncrono, então o asyncio não troca de contexto entre o insert e o retorno — a
    UNIQUE em job_url é o guard atômico contra duas chamadas concorrentes avaliarem
    a mesma URL. Devolve False quando a URL já foi reservada."""
    try:
        ScanLog.create(job_url=raw.url, source=raw.source)
        return True
    except IntegrityError:
        return False


def _release(raw: RawJob) -> None:
    """Libera o claim para retry num scan futuro (nunca deixa claim órfão)."""
    ScanLog.delete().where(ScanLog.job_url == raw.url).execute()


def _persist(raw: RawJob, **scoring: Any) -> Job | None:
    """Salva o RawJob como Job com os campos de scoring. None se a URL já existe."""
    try:
        job: Job = Job.create(
            source=raw.source,
            company=raw.company,
            title=raw.title,
            url=raw.url,
            location=raw.location,
            remote_type=raw.remote_type,
            description=raw.description,
            posted_at=raw.posted_at,
            **scoring,
        )
        return job
    except IntegrityError:
        return None


async def _scan_linkedin(keywords: str, config: dict[str, Any]) -> tuple[list[RawJob], str | None]:
    """Scan do LinkedIn via Playwright (exige login prévio). Sessão expirada vira
    aviso; qualquer outra falha — inclusive não haver browser — é silenciosa para
    não bloquear os resultados HTTP."""
    from candidatador.discovery.sources.playwright import (
        LinkedInScanner,
        LinkedInSessionExpiredError,
    )

    try:
        page = await browser.new_page(config)
    except Exception:
        return [], None
    try:
        jobs = await LinkedInScanner(page).scan(keywords=keywords or "software engineer")
        return jobs, None
    except LinkedInSessionExpiredError as e:
        return [], f"⚠️  LinkedIn: {e}"
    except Exception:
        return [], None
    finally:
        await page.close()


async def _collect_raw_jobs(
    keywords: str, config: dict[str, Any], companies: dict[str, list[str]]
) -> tuple[list[RawJob], str | None]:
    """Coleta vagas das fontes HTTP e do LinkedIn. Devolve as vagas brutas e um
    aviso opcional do LinkedIn."""
    scanners = {
        "greenhouse": GreenhouseScanner(),
        "lever": LeverScanner(),
        "ashby": AshbyScanner(),
    }
    raw_jobs: list[RawJob] = []
    for source, scanner in scanners.items():
        slugs = companies.get(source, [])
        if slugs:
            raw_jobs.extend(await scanner.scan(slugs))

    li_jobs, li_warning = await _scan_linkedin(keywords, config)
    raw_jobs.extend(li_jobs)
    return raw_jobs, li_warning


def _drop_already_seen(raw_jobs: list[RawJob]) -> list[RawJob]:
    seen = {row.job_url for row in ScanLog.select(ScanLog.job_url)}
    return [j for j in raw_jobs if j.url not in seen]


async def _evaluate_and_store(
    new_jobs: list[RawJob], config: dict[str, Any], profile: dict[str, Any], caller: LLMCaller
) -> tuple[list[Job], bool]:
    """Avalia e salva cada vaga em lotes concorrentes, parando conservadoramente no
    primeiro spend limit ou erro inesperado. Devolve as vagas salvas e se parou."""
    threshold = config["score_threshold"]
    model = _model_for(config)
    blocklist: list[str] = config.get("title_blocklist", [])
    stop = asyncio.Event()

    async def evaluate_one(raw: RawJob) -> Job | None | _StopScan:
        if not _claim(raw):
            return None
        if stop.is_set():
            _release(raw)
            return _StopScan()

        matched = should_skip_by_title(raw.title, blocklist)
        if matched:
            return _persist(
                raw,
                score=0.0,
                score_notes=f"title filtered: {matched!r}",
                caveats="[]",
                status="archived",
            )

        try:
            result = await evaluate_job(
                company=raw.company,
                title=raw.title,
                description=raw.description or f"{raw.title} at {raw.company}",
                profile=profile,
                model=model,
                _caller=caller,
            )
        except Exception as e:
            _release(raw)
            if _is_spend_limit(e):
                stop.set()
                return _StopScan()
            logger.error("scan: erro inesperado avaliando %s/%s — %s", raw.company, raw.title, e)
            raise

        return _persist(
            raw,
            score=result.score,
            score_notes=result.score_notes,
            caveats=json.dumps(result.caveats),
            salary_min=result.salary_min,
            salary_max=result.salary_max,
            salary_currency=result.salary_currency,
            salary_source=result.salary_source,
            status="new" if result.score >= threshold else "archived",
        )

    saved: list[Job] = []
    spend_hit = False
    for start in range(0, len(new_jobs), BATCH_SIZE):
        # Guarda defensiva: na prática inalcançável — quem seta stop sempre devolve um
        # _StopScan no MESMO batch, que já dispara o break abaixo antes de reentrar.
        if stop.is_set():  # pragma: no cover
            spend_hit = True
            break
        batch = new_jobs[start : start + BATCH_SIZE]
        # return_exceptions=True: nenhuma coroutine é cancelada — cada uma roda até o
        # fim e limpa o próprio claim, eliminando claims órfãos.
        outcomes = await asyncio.gather(*map(evaluate_one, batch), return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, _StopScan):
                spend_hit = True
            elif isinstance(outcome, BaseException):
                logger.error("scan: coroutine falhou — %s", outcome)
                spend_hit = True
            elif outcome is not None:
                saved.append(outcome)
        if spend_hit:
            break

    if spend_hit:
        logger.warning("scan_and_evaluate: interrompido por spend limit após %d vagas", len(saved))
    return saved, spend_hit


def _with_warning(message: str, warning: str | None) -> str:
    return f"{message}\n\n{warning}" if warning else message


def _format_report(saved: list[Job], spend_hit: bool, threshold: float) -> str:
    above = [j for j in saved if j.status == "new"]
    title_filtered = sum(
        1 for j in saved if j.score_notes and j.score_notes.startswith("title filtered:")
    )
    below = len(saved) - len(above) - title_filtered
    spend_note = (
        "\n\n⚠️  Spend limit atingido — scan interrompido (vagas restantes ficam para o próximo scan)."
        if spend_hit
        else ""
    )

    if not above:
        return (
            f"{len(saved)} vagas processadas. Nenhuma passou o threshold de {threshold}. "
            f"({title_filtered} descartadas por título, {below} abaixo do score){spend_note}"
        )

    table = render_jobs_table(above)
    footer = (
        f"\n∗ = salário estimado pelo LLM  |  "
        f"{below} abaixo do threshold  |  {title_filtered} descartadas por título"
    )
    return (
        f"{len(saved)} vagas processadas. {len(above)} acima do threshold:"
        f"\n\n{table}{footer}{spend_note}"
    )


async def scan_and_evaluate(
    keywords: str, phase: str, config: dict[str, Any], profile: dict[str, Any], caller: LLMCaller
) -> str:
    companies = load_company_list(phase=None if phase == "all" else phase)
    raw_jobs, li_warning = await _collect_raw_jobs(keywords, config, companies)
    new_jobs = _drop_already_seen(raw_jobs)
    if not new_jobs:
        return _with_warning("Nenhuma vaga nova encontrada.", li_warning)

    saved, spend_hit = await _evaluate_and_store(new_jobs, config, profile, caller)
    return _with_warning(_format_report(saved, spend_hit, config["score_threshold"]), li_warning)


async def add_job(
    url: str,
    company: str,
    title: str,
    description: str,
    config: dict[str, Any],
    profile: dict[str, Any],
    caller: LLMCaller,
) -> str:
    threshold = config["score_threshold"]
    model = _model_for(config)
    blocklist: list[str] = config.get("title_blocklist", [])

    if not description:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "candidatador/0.1"})
            if r.status_code != 200:
                return (
                    f"Não consegui buscar a URL (HTTP {r.status_code}). "
                    f"Forneça 'description' manualmente."
                )
            description = re.sub(r"<[^>]+>", " ", r.text).strip()
            description = re.sub(r"\s+", " ", description)[:8000]
        except Exception as e:
            return (
                f"Erro ao buscar URL: {e}\n"
                f"Para páginas que requerem login (LinkedIn, etc.), forneça "
                f"'company', 'title' e 'description' manualmente."
            )

    if not company or not title:
        return "Forneça pelo menos 'company' e 'title' junto com a URL."

    if ScanLog.select().where(ScanLog.job_url == url).exists():
        try:
            existing = Job.get(Job.url == url)
            return (
                f"Vaga já existe no banco "
                f"(id={existing.id}, score={existing.score:.1f}, status={existing.status})."
            )
        except Job.DoesNotExist:
            pass

    matched = should_skip_by_title(title, blocklist)
    if matched:
        try:
            Job.create(
                source="manual",
                company=company,
                title=title,
                url=url,
                location=None,
                remote_type=None,
                description=description,
                posted_at=None,
                score=0.0,
                score_notes=f"title filtered: {matched!r}",
                caveats="[]",
                status="archived",
            )
            ScanLog.create(job_url=url, source="manual")
        except IntegrityError:
            pass
        return f"Vaga descartada pelo filtro de título (padrão: {matched!r})."

    result = await evaluate_job(
        company=company,
        title=title,
        description=description,
        profile=profile,
        model=model,
        _caller=caller,
    )

    status = "new" if result.score >= threshold else "archived"
    try:
        job = Job.create(
            source="manual",
            company=company,
            title=title,
            url=url,
            location=None,
            remote_type=None,
            description=description,
            posted_at=None,
            score=result.score,
            score_notes=result.score_notes,
            caveats=json.dumps(result.caveats),
            salary_min=result.salary_min,
            salary_max=result.salary_max,
            salary_currency=result.salary_currency,
            salary_source=result.salary_source,
            status=status,
        )
        ScanLog.create(job_url=url, source="manual")
    except IntegrityError:
        return "Vaga já existe no banco (conflito de URL)."

    icon = "✓ NEW" if status == "new" else "arquivada"
    caveats_str = (
        "\n".join(f"  ⚠ {c}" for c in result.caveats) if result.caveats else "  nenhum"
    )
    return (
        f"{icon} — {company} / {title}\n"
        f"Score: {result.score:.1f}/10  (threshold: {threshold})\n"
        f"Notas: {result.score_notes}\n"
        f"Caveats:\n{caveats_str}\n"
        f"id={job.id}"
    )
