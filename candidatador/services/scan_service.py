"""Serviço de scan: descobre vagas (HTTP + LinkedIn), avalia com LLM e salva.

As tools MCP em mcp_server são wrappers finos que chamam estas funções passando
config/profile/caller. A lógica fica aqui, testável isolada.
"""

import asyncio
import json
import re
from typing import Any

import httpx
from peewee import IntegrityError

from candidatador import browser
from candidatador.config import load_company_list
from candidatador.db import Job, ScanLog
from candidatador.evaluator import evaluate_job, should_skip_by_title
from candidatador.llm import LLMCaller
from candidatador.log import get_logger
from candidatador.scanner.base import RawJob
from candidatador.scanner.http_sources import AshbyScanner, GreenhouseScanner, LeverScanner
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


async def scan_and_evaluate(
    keywords: str, phase: str, config: dict[str, Any], profile: dict[str, Any], caller: LLMCaller
) -> str:
    threshold = config["score_threshold"]
    model = config.get("eval_model", config.get("llm_model", "claude-haiku-4-5-20251001"))
    blocklist: list[str] = config.get("title_blocklist", [])

    effective_phase = None if phase == "all" else phase
    companies = load_company_list(phase=effective_phase)

    # Fetch raw jobs from HTTP sources
    scanners = {
        "greenhouse": GreenhouseScanner(),
        "lever": LeverScanner(),
        "ashby": AshbyScanner(),
    }
    all_raw = []
    for source, scanner in scanners.items():
        slugs = companies.get(source, [])
        if slugs:
            raw = await scanner.scan(slugs)
            all_raw.extend(raw)

    # LinkedIn scan (Playwright — requires prior login)
    from candidatador.scanner.playwright_sources import (
        LinkedInScanner,
        LinkedInSessionExpiredError,
    )

    li_warning: str | None = None
    try:
        li_page = await browser.new_page(config)
        try:
            li_scanner = LinkedInScanner(li_page)
            li_jobs = await li_scanner.scan(keywords=keywords or "software engineer")
            all_raw.extend(li_jobs)
        except LinkedInSessionExpiredError as e:
            li_warning = f"⚠️  LinkedIn: {e}"
        except Exception:
            pass  # outros erros do LinkedIn não bloqueiam resultados HTTP
        finally:
            await li_page.close()
    except Exception:
        pass  # new_page() falhou — sem browser disponível

    # Dedup against scan_log
    seen_urls = {row.job_url for row in ScanLog.select(ScanLog.job_url)}
    new_raw = [j for j in all_raw if j.url not in seen_urls]

    def _with_li_warning(msg: str) -> str:
        return f"{msg}\n\n{li_warning}" if li_warning else msg

    if not new_raw:
        return _with_li_warning("Nenhuma vaga nova encontrada.")

    results: list[Job] = []

    # Sentinela retornada por uma coroutine que detectou spend limit.
    class _StopScan:
        pass

    stop_event = asyncio.Event()

    async def _eval_and_save(raw: RawJob) -> Job | None | _StopScan:
        # Claim the URL in ScanLog before any work. ScanLog.create is synchronous
        # (no await), so asyncio won't context-switch between the insert and its
        # return — the UNIQUE constraint on job_url makes this the atomic guard
        # against concurrent scan_and_evaluate calls evaluating the same URL twice.
        try:
            ScanLog.create(job_url=raw.url, source=raw.source)
        except IntegrityError:
            return None  # already claimed or processed by a concurrent call

        # Se uma irmã já bateu o limite, libera o claim e sai sem gastar token.
        if stop_event.is_set():
            ScanLog.delete().where(ScanLog.job_url == raw.url).execute()
            return _StopScan()

        matched_pattern = should_skip_by_title(raw.title, blocklist)
        if matched_pattern:
            try:
                filtered: Job = Job.create(
                    source=raw.source,
                    company=raw.company,
                    title=raw.title,
                    url=raw.url,
                    location=raw.location,
                    remote_type=raw.remote_type,
                    description=raw.description,
                    posted_at=raw.posted_at,
                    score=0.0,
                    score_notes=f"title filtered: {matched_pattern!r}",
                    caveats="[]",
                    status="archived",
                )
                return filtered
            except IntegrityError:
                return None

        try:
            eval_result = await evaluate_job(
                company=raw.company,
                title=raw.title,
                description=raw.description or f"{raw.title} at {raw.company}",
                profile=profile,
                model=model,
                _caller=caller,
            )
        except Exception as e:
            # Falhou: libera o claim para retry num scan futuro (nunca órfão).
            ScanLog.delete().where(ScanLog.job_url == raw.url).execute()
            if _is_spend_limit(e):
                stop_event.set()
                return _StopScan()
            # Erro inesperado: NÃO silenciar — loga e devolve como exceção.
            logger.error("scan: erro inesperado avaliando %s/%s — %s", raw.company, raw.title, e)
            raise

        try:
            saved: Job = Job.create(
                source=raw.source,
                company=raw.company,
                title=raw.title,
                url=raw.url,
                location=raw.location,
                remote_type=raw.remote_type,
                description=raw.description,
                posted_at=raw.posted_at,
                score=eval_result.score,
                score_notes=eval_result.score_notes,
                caveats=json.dumps(eval_result.caveats),
                salary_min=eval_result.salary_min,
                salary_max=eval_result.salary_max,
                salary_currency=eval_result.salary_currency,
                salary_source=eval_result.salary_source,
                status="new" if eval_result.score >= threshold else "archived",
            )
            return saved
        except IntegrityError:
            return None

    spend_hit = False
    for i in range(0, len(new_raw), BATCH_SIZE):
        if stop_event.is_set():
            spend_hit = True
            break
        batch = new_raw[i : i + BATCH_SIZE]
        # return_exceptions=True: nenhuma coroutine é cancelada — cada uma roda
        # até o fim e limpa o próprio claim. Isso elimina claims órfãos.
        batch_results = await asyncio.gather(
            *[_eval_and_save(raw) for raw in batch], return_exceptions=True
        )
        for r in batch_results:
            if isinstance(r, _StopScan):
                spend_hit = True
            elif isinstance(r, BaseException):
                logger.error("scan: coroutine falhou — %s", r)
                spend_hit = True  # para conservadoramente em erro inesperado
            elif r is not None:
                results.append(r)
        if spend_hit:
            break

    if spend_hit:
        logger.warning(
            "scan_and_evaluate: interrompido por spend limit após %d vagas", len(results)
        )

    above = [j for j in results if j.status == "new"]
    title_filtered = sum(
        1 for j in results if j.score_notes and j.score_notes.startswith("title filtered:")
    )
    below = len(results) - len(above) - title_filtered
    spend_note = (
        "\n\n⚠️  Spend limit atingido — scan interrompido (vagas restantes ficam para o próximo scan)."
        if spend_hit
        else ""
    )

    if not above:
        return _with_li_warning(
            f"{len(results)} vagas processadas. Nenhuma passou o threshold de {threshold}. "
            f"({title_filtered} descartadas por título, {below} abaixo do score){spend_note}"
        )

    table = render_jobs_table(above)
    footer = (
        f"\n∗ = salário estimado pelo LLM  |  "
        f"{below} abaixo do threshold  |  {title_filtered} descartadas por título"
    )
    return _with_li_warning(
        f"{len(results)} vagas processadas. {len(above)} acima do threshold:\n\n{table}{footer}{spend_note}"
    )


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
    model = config.get("eval_model", config.get("llm_model", "claude-haiku-4-5-20251001"))
    blocklist: list[str] = config.get("title_blocklist", [])

    # Tenta buscar descrição automaticamente se não foi fornecida
    if not description:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "candidatador/0.1"})
            if r.status_code == 200:
                description = re.sub(r"<[^>]+>", " ", r.text).strip()
                description = re.sub(r"\s+", " ", description)[:8000]
            else:
                return (
                    f"Não consegui buscar a URL (HTTP {r.status_code}). "
                    f"Forneça 'description' manualmente."
                )
        except Exception as e:
            return (
                f"Erro ao buscar URL: {e}\n"
                f"Para páginas que requerem login (LinkedIn, etc.), forneça "
                f"'company', 'title' e 'description' manualmente."
            )

    if not company or not title:
        return "Forneça pelo menos 'company' e 'title' junto com a URL."

    # Verifica duplicata
    if ScanLog.select().where(ScanLog.job_url == url).exists():
        try:
            job = Job.get(Job.url == url)
            return f"Vaga já existe no banco (id={job.id}, score={job.score:.1f}, status={job.status})."
        except Job.DoesNotExist:
            pass

    # Filtro de título
    matched_pattern = should_skip_by_title(title, blocklist)
    if matched_pattern:
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
                score=0.0,
                score_notes=f"title filtered: {matched_pattern!r}",
                caveats="[]",
                status="archived",
            )
            ScanLog.create(job_url=url, source="manual")
        except IntegrityError:
            pass
        return f"Vaga descartada pelo filtro de título (padrão: {matched_pattern!r})."

    # Avaliação LLM
    eval_result = await evaluate_job(
        company=company,
        title=title,
        description=description,
        profile=profile,
        model=model,
        _caller=caller,
    )

    status = "new" if eval_result.score >= threshold else "archived"
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
            score=eval_result.score,
            score_notes=eval_result.score_notes,
            caveats=json.dumps(eval_result.caveats),
            salary_min=eval_result.salary_min,
            salary_max=eval_result.salary_max,
            salary_currency=eval_result.salary_currency,
            salary_source=eval_result.salary_source,
            status=status,
        )
        ScanLog.create(job_url=url, source="manual")
    except IntegrityError:
        return "Vaga já existe no banco (conflito de URL)."

    icon = "✓ NEW" if status == "new" else "arquivada"
    caveats_str = (
        "\n".join(f"  ⚠ {c}" for c in eval_result.caveats) if eval_result.caveats else "  nenhum"
    )
    return (
        f"{icon} — {company} / {title}\n"
        f"Score: {eval_result.score:.1f}/10  (threshold: {threshold})\n"
        f"Notas: {eval_result.score_notes}\n"
        f"Caveats:\n{caveats_str}\n"
        f"id={job.id}"
    )
