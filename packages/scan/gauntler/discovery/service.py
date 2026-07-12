"""Serviço de scan: descobre vagas (HTTP + LinkedIn), avalia com LLM e salva.

As tools MCP em server.py são wrappers finos que chamam estas funções passando
config/profile/caller. A lógica fica aqui, testável isolada.
"""

import asyncio
import datetime
import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from gauntler.core import browser
from gauntler.core.config import load_company_list
from gauntler.core.db import Job, ScanLog
from gauntler.core.llm import LLMCaller, is_spend_limit
from gauntler.core.log import get_logger
from gauntler.discovery.evaluator import (
    EvalInput,
    evaluate_job,
    evaluate_jobs_batch,
    should_skip_by_title,
)
from gauntler.discovery.sources.base import RawJob
from gauntler.discovery.sources.http import AshbyScanner, GreenhouseScanner, LeverScanner
from gauntler.discovery.staleness import find_stale_jobs
from gauntler.views import render_jobs_table
from peewee import IntegrityError, fn

logger = get_logger(__name__)


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
    from gauntler.discovery.sources.playwright import (
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
    """Avalia e salva as vagas em LOTES concorrentes (até scan_concurrency lotes em
    paralelo, scan_batch_size vagas por lote), parando no primeiro spend limit ou erro
    inesperado. Devolve as vagas salvas e se parou."""
    threshold = config["score_threshold"]
    model = _model_for(config)
    blocklist: list[str] = config.get("title_blocklist", [])
    concurrency: int = config.get("scan_concurrency", 5)
    batch_size: int = config.get("scan_batch_size", 5)
    stop = asyncio.Event()
    semaphore = asyncio.Semaphore(concurrency)

    async def evaluate_chunk(chunk: list[RawJob]) -> list[Job | _StopScan]:
        async with semaphore:
            # Já parou enquanto esperava o permit: não reserva nem chama o LLM.
            if stop.is_set():
                return [_StopScan()]

            results: list[Job | _StopScan] = []
            to_eval: list[RawJob] = []
            for raw in chunk:
                if not _claim(raw):
                    continue  # já reservada (corrida/scan anterior)
                matched = should_skip_by_title(raw.title, blocklist)
                if matched:
                    job = _persist(
                        raw,
                        score=0.0,
                        score_notes=f"title filtered: {matched!r}",
                        caveats="[]",
                        status="archived",
                    )
                    if job is not None:
                        results.append(job)
                else:
                    to_eval.append(raw)

            if not to_eval:
                return results

            try:
                evals = await evaluate_jobs_batch(
                    [
                        EvalInput(r.company, r.title, r.description or f"{r.title} at {r.company}")
                        for r in to_eval
                    ],
                    profile,
                    model,
                    caller,
                )
            except Exception as e:
                for raw in to_eval:
                    _release(raw)
                if is_spend_limit(e):
                    stop.set()
                    results.append(_StopScan())
                    return results
                logger.error("scan: erro inesperado no lote — %s", e)
                # Devolve results (title-filtered jobs já persistidos neste chunk) em
                # vez de propagar — a exceção crua faria o gather() descartar o chunk
                # inteiro do relatório, sub-contando vagas que já estão salvas no banco.
                results.append(_StopScan())
                return results

            for raw, result in zip(to_eval, evals, strict=True):
                job = _persist(
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
                if job is not None:
                    results.append(job)
            return results

    chunks = [new_jobs[i : i + batch_size] for i in range(0, len(new_jobs), batch_size)]
    chunk_outcomes = await asyncio.gather(*map(evaluate_chunk, chunks), return_exceptions=True)

    saved: list[Job] = []
    spend_hit = False
    for outcome in chunk_outcomes:
        if isinstance(outcome, BaseException):
            logger.error("scan: lote falhou — %s", outcome)
            spend_hit = True
            continue
        for item in outcome:
            if isinstance(item, _StopScan):
                spend_hit = True
            else:
                saved.append(item)

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

    if new_jobs:
        saved, spend_hit = await _evaluate_and_store(new_jobs, config, profile, caller)
        report = _format_report(saved, spend_hit, config["score_threshold"])
    else:
        report = "Nenhuma vaga nova encontrada."

    archive_result = await archive_stale_jobs(None, None, config)
    report = f"{report}\n\n{_format_archive_result(archive_result)}"

    return _with_warning(report, li_warning)


async def add_job(
    url: str,
    company: str,
    title: str,
    description: str,
    config: dict[str, Any],
    profile: dict[str, Any],
    caller: LLMCaller,
) -> str:
    if not description:
        fetched, error = await _fetch_description(url)
        if error:
            return error
        description = fetched or ""
    if not company or not title:
        return "Forneça pelo menos 'company' e 'title' junto com a URL."

    already = _existing_job_message(url)
    if already:
        return already

    matched = should_skip_by_title(title, config.get("title_blocklist", []))
    if matched:
        _persist_manual(
            company,
            title,
            url,
            description,
            score=0.0,
            score_notes=f"title filtered: {matched!r}",
            caveats="[]",
            status="archived",
        )
        return f"Vaga descartada pelo filtro de título (padrão: {matched!r})."

    threshold = config["score_threshold"]
    result = await evaluate_job(
        company=company,
        title=title,
        description=description,
        profile=profile,
        model=_model_for(config),
        _caller=caller,
    )
    status = "new" if result.score >= threshold else "archived"
    job = _persist_manual(
        company,
        title,
        url,
        description,
        score=result.score,
        score_notes=result.score_notes,
        caveats=json.dumps(result.caveats),
        salary_min=result.salary_min,
        salary_max=result.salary_max,
        salary_currency=result.salary_currency,
        salary_source=result.salary_source,
        status=status,
    )
    if job is None:
        return "Vaga já existe no banco (conflito de URL)."
    return _format_add_result(job, company, title, result, threshold, status)


async def _fetch_description(url: str) -> tuple[str | None, str | None]:
    """Busca e limpa (sem HTML) a descrição da vaga. Devolve (descrição, erro) — só
    um dos dois é não-nulo. Não funciona em páginas que exigem login."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "gauntler/0.1"})
        if r.status_code != 200:
            return None, (
                f"Não consegui buscar a URL (HTTP {r.status_code}). "
                f"Forneça 'description' manualmente."
            )
        text = re.sub(r"<[^>]+>", " ", r.text).strip()
        return re.sub(r"\s+", " ", text)[:8000], None
    except Exception as e:
        return None, (
            f"Erro ao buscar URL: {e}\n"
            f"Para páginas que requerem login (LinkedIn, etc.), forneça "
            f"'company', 'title' e 'description' manualmente."
        )


def _existing_job_message(url: str) -> str | None:
    """Mensagem de 'já existe' se a URL já está no banco; None caso contrário."""
    if not ScanLog.select().where(ScanLog.job_url == url).exists():
        return None
    try:
        job = Job.get(Job.url == url)
    except Job.DoesNotExist:
        return None
    return f"Vaga já existe no banco (id={job.id}, score={job.score:.1f}, status={job.status})."


def _persist_manual(
    company: str, title: str, url: str, description: str, **scoring: Any
) -> Job | None:
    """Salva uma vaga manual (source='manual') + o claim no ScanLog. None se a URL
    já existe (corrida/conflito)."""
    try:
        job: Job = Job.create(
            source="manual",
            company=company,
            title=title,
            url=url,
            location=None,
            remote_type=None,
            description=description,
            posted_at=None,
            **scoring,
        )
        ScanLog.create(job_url=url, source="manual")
        return job
    except IntegrityError:
        return None


def _format_add_result(
    job: Job, company: str, title: str, result: Any, threshold: float, status: str
) -> str:
    icon = "✓ NEW" if status == "new" else "arquivada"
    caveats_str = "\n".join(f"  ⚠ {c}" for c in result.caveats) if result.caveats else "  nenhum"
    return (
        f"{icon} — {company} / {title}\n"
        f"Score: {result.score:.1f}/10  (threshold: {threshold})\n"
        f"Notas: {result.score_notes}\n"
        f"Caveats:\n{caveats_str}\n"
        f"id={job.id}"
    )


# ── archive_stale_jobs ──────────────────────────────────────────────────────

ELIGIBLE_STATUSES = ("new", "reviewed", "applying", "needs_review")


class ArchiveStaleJobsError(ValueError):
    """Raised when job_id and company are both given (mutually exclusive filters)."""


@dataclass
class ArchiveResult:
    """Outcome of an archive_stale_jobs run."""

    archived: list[dict[str, str]] = field(default_factory=list)
    failed_companies: list[str] = field(default_factory=list)


def _eligible_jobs_query(job_id: int | None, company: str | None) -> Any:
    query = Job.select().where(Job.status.in_(ELIGIBLE_STATUSES))
    if job_id is not None:
        query = query.where(Job.id == job_id)
    elif company is not None:
        query = query.where(fn.LOWER(Job.company) == company.lower())
    return query


def _group_by_source_company(jobs: list[Job]) -> dict[tuple[str, str], list[Job]]:
    groups: dict[tuple[str, str], list[Job]] = {}
    for job in jobs:
        groups.setdefault((job.source, job.company), []).append(job)
    return groups


async def archive_stale_jobs(
    job_id: int | None, company: str | None, config: dict[str, Any]
) -> ArchiveResult:
    """Detects and archives (status='closed') eligible jobs that disappeared from
    their source. Mutually exclusive filters: job_id, company, or neither (all)."""
    if job_id is not None and company is not None:
        raise ArchiveStaleJobsError("Provide job_id OR company, not both.")

    jobs = list(_eligible_jobs_query(job_id, company))
    jobs_by_company = _group_by_source_company(jobs)
    scanners: dict[str, Any] = {
        "greenhouse": GreenhouseScanner(),
        "lever": LeverScanner(),
        "ashby": AshbyScanner(),
    }
    staleness = await find_stale_jobs(jobs_by_company, scanners, config)

    now = datetime.datetime.now()
    archived: list[dict[str, str]] = []
    for job in staleness.stale:
        job.status = "closed"
        job.closed_at = now
        job.save()
        archived.append({"company": job.company, "title": job.title, "url": job.url})

    return ArchiveResult(archived=archived, failed_companies=staleness.failed_companies)


def _format_archive_result(result: ArchiveResult) -> str:
    if not result.archived and not result.failed_companies:
        return "Nenhuma vaga fechada encontrada."
    lines: list[str] = []
    if result.archived:
        lines.append(f"{len(result.archived)} vaga(s) arquivada(s) (fechada na fonte):")
        lines.extend(f"  - {j['company']} / {j['title']} — {j['url']}" for j in result.archived)
    else:
        lines.append("Nenhuma vaga fechada encontrada.")
    if result.failed_companies:
        lines.append("")
        lines.append(f"⚠️  Não foi possível checar: {', '.join(result.failed_companies)}")
    return "\n".join(lines)
