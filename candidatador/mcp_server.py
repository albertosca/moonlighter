import asyncio
import contextlib
import json
import re
import secrets
import shutil
import time as _time
from datetime import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from peewee import IntegrityError
from rich.table import Table
from rich.console import Console
from rich import box
import io

from candidatador.db import init_db, Job, ScanLog, Application
from candidatador.config import load_config, load_profile, load_company_list
from candidatador.scanner.http_sources import GreenhouseScanner, LeverScanner, AshbyScanner
from candidatador.evaluator import evaluate_job, should_skip_by_title
from candidatador import browser as _browser_mod
import os
from candidatador.applicator.greenhouse import GreenhouseApplier
from candidatador.applicator.lever import LeverApplier
from candidatador.applicator.ashby import AshbyApplier
from candidatador.applicator.linkedin import LinkedInApplier
from candidatador.applicator.base import generate_answers

from candidatador.startup import validate_startup
from candidatador.llm import make_caller
from candidatador.email_monitor import (
    setup_gmail_service, sync_responses, _run_gmail_oauth, GmailAuthError
)
from candidatador.log import setup as _setup_logging, get_logger as _get_logger
_setup_logging()
_log = _get_logger(__name__)

_SPEND_LIMIT_MARKERS = (
    "spend limit", "quota", "rate limit", "too many requests",
    "overloaded", "429", "usage limit",
)


def _is_spend_limit(exc: Exception) -> bool:
    """True se a exceção indica esgotamento de cota/limite de gasto do LLM."""
    msg = str(exc).lower()
    return any(m in msg for m in _SPEND_LIMIT_MARKERS)


class CVNotFoundError(Exception):
    """O arquivo de CV resolvido para a empresa não existe no disco."""


def _resolve_cv_path(company: str, config: dict) -> str:
    """
    Resolve o caminho do CV para a empresa a partir de config['cv'].
    Match por empresa é case-insensitive. Cai no 'default' quando não há
    mapeamento. Caminhos relativos são resolvidos a partir da raiz do projeto.
    Levanta CVNotFoundError se o arquivo escolhido não existir (nunca sobe
    um CV errado em silêncio).
    """
    cv_cfg = config.get("cv", {}) or {}
    by_company = {k.lower(): v for k, v in (cv_cfg.get("by_company", {}) or {}).items()}
    rel = by_company.get((company or "").lower(), cv_cfg.get("default"))
    if not rel:
        raise CVNotFoundError(
            f"Sem CV mapeado para '{company}' e sem 'cv.default' em config. Verifique config.yaml/config.py."
        )
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = rel if os.path.isabs(rel) else os.path.join(project_root, rel)
    if not os.path.exists(path):
        raise CVNotFoundError(
            f"CV para '{company}' não encontrado em {path}. Verifique o mapeamento 'cv' na config."
        )
    return path


mcp = FastMCP("candidatador")
_config = load_config()
try:
    _profile = load_profile()
except FileNotFoundError:
    _profile = {}
_companies = load_company_list()
init_db()
_llm_caller = make_caller(_config)


def _log_tool(name: str):
    """Context manager que loga start/end com elapsed de cada ferramenta MCP."""
    @contextlib.asynccontextmanager
    async def _ctx():
        _log.info("tool=%s start", name)
        t0 = _time.monotonic()
        try:
            yield
        finally:
            _log.info("tool=%s end elapsed=%.1fs", name, _time.monotonic() - t0)
    return _ctx()

_startup_warnings = validate_startup(_config, _profile)
for _w in _startup_warnings:
    _prefix = "🚫" if _w.level == "error" else "⚠️ "
    print(f"{_prefix} {_w.message}", flush=True)


def _render_table(jobs: list[Job]) -> str:
    buf = io.StringIO()
    console = Console(file=buf, width=120)
    table = Table(box=box.SIMPLE_HEAVY, show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Empresa / Cargo", min_width=28)
    table.add_column("Score", width=7)
    table.add_column("Salário", width=14)
    table.add_column("Publicada", width=11)
    table.add_column("Remoto", width=8)
    table.add_column("Caveats", min_width=20)

    for job in jobs:
        score_str = f"{job.score:.1f}" if job.score is not None else "—"
        if job.salary_min and job.salary_max:
            sal = f"${job.salary_min//1000}–{job.salary_max//1000}k"
            if job.salary_source == "llm_estimate":
                sal += " *"
        elif job.salary_min:
            sal = f"${job.salary_min//1000}k+"
        else:
            sal = "n/d"
        posted = job.posted_at.strftime("%d/%m") if job.posted_at else "—"
        caveats_list = job.get_caveats()
        caveat_str = caveats_list[0][:30] if caveats_list else "—"
        table.add_row(
            str(job.id), f"{job.company} / {job.title}",
            score_str, sal, posted,
            job.remote_type or "—", caveat_str,
        )
    console.print(table)
    return buf.getvalue()


_APPLIER_CLASSES = [LinkedInApplier, GreenhouseApplier, LeverApplier, AshbyApplier]

async def _detect_applier(page, config, profile):
    for cls in _APPLIER_CLASSES:
        applier = cls(page, config, profile)
        if await applier.detect():
            return applier
    return None


@mcp.tool()
async def scan_and_evaluate(keywords: str = "", phase: str = "phase1") -> str:
    """Scan job boards, evaluate with LLM, return new jobs above threshold.

    Por padrão escaneia só a fase 1 (empresas BR prioritárias) para economizar tokens.
    Use phase='phase2', 'phase3', ou 'all' para escanear mais empresas explicitamente.

    Args:
        keywords: palavras-chave para o scanner LinkedIn (opcional)
        phase: "phase1" (padrão/BR), "phase2" (remote-first global),
               "phase3" (big techs), ou "all" (tudo)
    """
    async with _log_tool("scan_and_evaluate"):
        threshold = _config["score_threshold"]
        model = _config.get("eval_model", _config.get("llm_model", "claude-haiku-4-5-20251001"))
        blocklist: list[str] = _config.get("title_blocklist", [])

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
        from candidatador.scanner.playwright_sources import LinkedInScanner, LinkedInSessionExpiredError
        _li_warning: str | None = None
        try:
            li_page = await _browser_mod.new_page(_config)
            try:
                li_scanner = LinkedInScanner(li_page)
                li_jobs = await li_scanner.scan(keywords=keywords or "software engineer")
                all_raw.extend(li_jobs)
            except LinkedInSessionExpiredError as e:
                _li_warning = f"⚠️  LinkedIn: {e}"
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
            return f"{msg}\n\n{_li_warning}" if _li_warning else msg

        if not new_raw:
            return _with_li_warning("Nenhuma vaga nova encontrada.")

        # Evaluate jobs concurrently in batches of 10
        BATCH_SIZE = 10
        results = []

        # Sentinela retornada por uma coroutine que detectou spend limit.
        class _StopScan:
            pass

        stop_event = asyncio.Event()

        async def _eval_and_save(raw) -> "Job | None | _StopScan":
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
                    return Job.create(
                        source=raw.source, company=raw.company, title=raw.title,
                        url=raw.url, location=raw.location, remote_type=raw.remote_type,
                        description=raw.description, posted_at=raw.posted_at,
                        score=0.0, score_notes=f"title filtered: {matched_pattern!r}",
                        caveats="[]", status="archived",
                    )
                except IntegrityError:
                    return None

            try:
                eval_result = await evaluate_job(
                    company=raw.company,
                    title=raw.title,
                    description=raw.description or f"{raw.title} at {raw.company}",
                    profile=_profile,
                    model=model,
                    _caller=_llm_caller,
                )
            except Exception as e:
                # Falhou: libera o claim para retry num scan futuro (nunca órfão).
                ScanLog.delete().where(ScanLog.job_url == raw.url).execute()
                if _is_spend_limit(e):
                    stop_event.set()
                    return _StopScan()
                # Erro inesperado: NÃO silenciar — loga e devolve como exceção.
                _log.error("scan: erro inesperado avaliando %s/%s — %s",
                           raw.company, raw.title, e)
                raise

            try:
                return Job.create(
                    source=raw.source, company=raw.company, title=raw.title,
                    url=raw.url, location=raw.location, remote_type=raw.remote_type,
                    description=raw.description, posted_at=raw.posted_at,
                    score=eval_result.score,
                    score_notes=eval_result.score_notes,
                    caveats=json.dumps(eval_result.caveats),
                    salary_min=eval_result.salary_min,
                    salary_max=eval_result.salary_max,
                    salary_currency=eval_result.salary_currency,
                    salary_source=eval_result.salary_source,
                    status="new" if eval_result.score >= threshold else "archived",
                )
            except IntegrityError:
                return None

        spend_hit = False
        for i in range(0, len(new_raw), BATCH_SIZE):
            if stop_event.is_set():
                spend_hit = True
                break
            batch = new_raw[i:i + BATCH_SIZE]
            # return_exceptions=True: nenhuma coroutine é cancelada — cada uma roda
            # até o fim e limpa o próprio claim. Isso elimina claims órfãos.
            batch_results = await asyncio.gather(
                *[_eval_and_save(raw) for raw in batch], return_exceptions=True
            )
            for r in batch_results:
                if isinstance(r, _StopScan):
                    spend_hit = True
                elif isinstance(r, Exception):
                    _log.error("scan: coroutine falhou — %s", r)
                    spend_hit = True  # para conservadoramente em erro inesperado
                elif r is not None:
                    results.append(r)
            if spend_hit:
                break

        if spend_hit:
            _log.warning("scan_and_evaluate: interrompido por spend limit após %d vagas", len(results))

        above = [j for j in results if j.status == "new"]
        title_filtered = sum(
            1 for j in results
            if j.score_notes and j.score_notes.startswith("title filtered:")
        )
        below = len(results) - len(above) - title_filtered
        spend_note = (
            "\n\n⚠️  Spend limit atingido — scan interrompido (vagas restantes ficam para o próximo scan)."
            if spend_hit else ""
        )

        if not above:
            return _with_li_warning(
                f"{len(results)} vagas processadas. Nenhuma passou o threshold de {threshold}. "
                f"({title_filtered} descartadas por título, {below} abaixo do score){spend_note}"
            )

        table = _render_table(above)
        footer = (
            f"\n∗ = salário estimado pelo LLM  |  "
            f"{below} abaixo do threshold  |  {title_filtered} descartadas por título"
        )
        return _with_li_warning(f"{len(results)} vagas processadas. {len(above)} acima do threshold:\n\n{table}{footer}{spend_note}")


@mcp.tool()
async def add_job(url: str, company: str = "", title: str = "", description: str = "") -> str:
    """Avalia uma vaga fornecida manualmente e salva no banco.

    Útil para vagas do LinkedIn, posts de emprego, ou qualquer fonte não suportada
    pelo scanner automático. Se 'description' não for fornecida, tenta buscar a
    URL via HTTP (não funciona para páginas que requerem autenticação, como LinkedIn).

    Args:
        url: URL da vaga (obrigatório, usado como identificador único)
        company: Nome da empresa (ex: "ifood")
        title: Título da vaga (ex: "Senior Software Engineer")
        description: Texto da descrição da vaga. Se vazio, tenta buscar automaticamente.
    """
    async with _log_tool("add_job"):
        threshold = _config["score_threshold"]
        model = _config.get("eval_model", _config.get("llm_model", "claude-haiku-4-5-20251001"))
        blocklist: list[str] = _config.get("title_blocklist", [])

        # Tenta buscar descrição automaticamente se não foi fornecida
        if not description:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    r = await client.get(url, headers={"User-Agent": "candidatador/0.1"})
                if r.status_code == 200:
                    description = re.sub(r'<[^>]+>', ' ', r.text).strip()
                    description = re.sub(r'\s+', ' ', description)[:8000]
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
                    source="manual", company=company, title=title,
                    url=url, location=None, remote_type=None,
                    description=description, posted_at=None,
                    score=0.0, score_notes=f"title filtered: {matched_pattern!r}",
                    caveats="[]", status="archived",
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
            profile=_profile,
            model=model,
            _caller=_llm_caller,
        )

        status = "new" if eval_result.score >= threshold else "archived"
        try:
            job = Job.create(
                source="manual", company=company, title=title,
                url=url, location=None, remote_type=None,
                description=description, posted_at=None,
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
        caveats_str = "\n".join(f"  ⚠ {c}" for c in eval_result.caveats) if eval_result.caveats else "  nenhum"
        return (
            f"{icon} — {company} / {title}\n"
            f"Score: {eval_result.score:.1f}/10  (threshold: {threshold})\n"
            f"Notas: {eval_result.score_notes}\n"
            f"Caveats:\n{caveats_str}\n"
            f"id={job.id}"
        )


@mcp.tool()
async def list_jobs(status: str = "new", limit: int = 20) -> str:
    """List jobs from DB filtered by status."""
    async with _log_tool("list_jobs"):
        jobs = list(Job.select().where(Job.status == status).order_by(Job.score.desc()).limit(limit))
        if not jobs:
            return f"Nenhuma vaga com status='{status}'."
        return _render_table(jobs)


@mcp.tool()
async def get_job(id: int) -> str:
    """Get full details of a job posting."""
    async with _log_tool("get_job"):
        try:
            job = Job.get_by_id(id)
        except Job.DoesNotExist:
            return f"Vaga #{id} não encontrada."
        caveats = job.get_caveats()
        score_str = f"{job.score:.1f}" if job.score is not None else "—"
        lines = [
            f"# {job.company} — {job.title}",
            f"**Source:** {job.source}  |  **Status:** {job.status}",
            f"**Score:** {score_str}/10  |  **Remoto:** {job.remote_type or 'n/d'}",
            f"**Publicada:** {job.posted_at.strftime('%d/%m/%Y') if job.posted_at else 'n/d'}",
            f"**URL:** {job.url}",
        ]
        if job.salary_min:
            sal = f"${job.salary_min:,}–${job.salary_max:,} {job.salary_currency}" if job.salary_max else f"${job.salary_min:,}+ {job.salary_currency}"
            lines.append(f"**Salário:** {sal} ({job.salary_source})")
        if caveats:
            lines.append(f"**Caveats:** {', '.join(caveats)}")
        lines.append(f"\n**Por quê esse score:** {job.score_notes}")
        lines.append(f"\n---\n{job.description or '(sem descrição)'}")
        return "\n".join(lines)


@mcp.tool()
async def login(platform: str = "linkedin") -> str:
    """Open Brave for manual login. Session is saved and reused in future scans."""
    async with _log_tool("login"):
        if platform != "linkedin":
            return f"Platform '{platform}' not supported yet. Supported: linkedin"
        page = await _browser_mod.new_page(_config)
        await page.goto("https://www.linkedin.com/login")
        return (
            "Brave aberto em linkedin.com/login. "
            "Faça login manualmente. "
            "A sessão será salva automaticamente em ~/.candidatador/browser-session/"
        )


@mcp.tool()
async def apply_jobs(ids: list[int]) -> str:
    """
    Start application flow for given job IDs.
    Opens each job in Brave, extracts form fields, generates LLM answers.
    Returns draft answers for review before submission.
    """
    async with _log_tool("apply_jobs"):
        drafts_output = []
        for job_id in ids:
            try:
                job = Job.get_by_id(job_id)
            except Job.DoesNotExist:
                drafts_output.append(f"⚠️  Vaga #{job_id} não encontrada.")
                continue

            page = await _browser_mod.new_page(_config)
            try:
                await page.goto(job.url, timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=15000)
                await _browser_mod.save_screenshot(page, job_id, "01-job-page", _config)

                applier = await _detect_applier(page, _config, _profile)
                if not applier:
                    drafts_output.append(f"⚠️  Vaga #{job_id}: ATS não reconhecido. URL: {job.url}")
                    continue

                if isinstance(applier, LinkedInApplier):
                    if not await applier.is_easy_apply():
                        drafts_output.append(
                            f"⚠️  Vaga #{job_id} ({job.company}/{job.title}): não tem Easy Apply. "
                            f"Candidatura manual necessária: {job.url}"
                        )
                        continue

                fields = await applier.extract_fields()
                await _browser_mod.save_screenshot(page, job_id, "02-form", _config)

                draft = await generate_answers(
                    company=job.company,
                    title=job.title,
                    description=job.description or "",
                    fields=fields,
                    profile=_profile,
                    model=_config["llm_model"],
                    job_id=job_id,
                    _caller=_llm_caller,
                    config=_config,
                    job_location=job.location,
                    job_remote_type=job.remote_type,
                )

                # Save draft to DB
                app, created = Application.get_or_create(
                    job=job,
                    defaults={"status": "draft", "form_data": json.dumps(draft.answers)}
                )
                if not created:
                    app.form_data = json.dumps(draft.answers)
                    app.status = "draft"
                    app.updated_at = datetime.now()
                    app.save()

                Job.update(status="applying").where(Job.id == job_id).execute()

                lines = [f"\n## Rascunho — Vaga #{job_id}: {job.company} / {job.title}"]
                if draft.error:
                    lines.append(f"⚠️ Erro ao gerar respostas: {draft.error}")
                needs_review = [f for f, a in draft.answers.items() if a == "__NEEDS_REVIEW__"]
                if needs_review:
                    lines.append(
                        "\n🚫 PRECISAM DA SUA DECISÃO (não preenchidos — autorização de "
                        "trabalho/visto, país da vaga indefinido):"
                    )
                    for f in needs_review:
                        lines.append(f"  - {f}")
                    lines.append(
                        f"Responda no confirm_apply: "
                        f"`confirm_apply(job_id={job_id}, answers={{\"<campo>\": \"Yes/No\"}})`"
                    )
                for field, answer in draft.answers.items():
                    if answer == "__NEEDS_REVIEW__":
                        continue
                    lines.append(f"\n**{field}**\n{answer}")
                lines.append(f"\nPara aprovar e candidatar: `confirm_apply(job_id={job_id})`")
                lines.append(f"Para editar: passe `answers={{\"campo\": \"nova resposta\"}}` no confirm_apply")
                drafts_output.append("\n".join(lines))

            except Exception as e:
                drafts_output.append(f"⚠️  Vaga #{job_id}: erro — {e}")
            finally:
                await page.close()

        return "\n\n---\n".join(drafts_output)


def _archive_screenshots(job_id: int, config: dict) -> None:
    """Move screenshots de candidatura concluída para subdir 'done/', liberando espaço."""
    try:
        src = Path(config["screenshots_dir"]) / str(job_id)
        if not src.exists():
            return
        dst = Path(config["screenshots_dir"]) / "done" / str(job_id)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))
        _log.info("_archive_screenshots: #%d → done/", job_id)
    except Exception as e:
        _log.debug("_archive_screenshots: falha (não crítico) — %s", e)


@mcp.tool()
async def confirm_apply(job_id: int, answers: dict | None = None) -> str:
    """
    Submit the application for a job.
    job_id: ID of the job (must have a draft Application in DB)
    answers: optional dict of {field: answer} overrides merged into the saved draft
    """
    async with _log_tool("confirm_apply"):
        try:
            job = Job.get_by_id(job_id)
            app = Application.get(Application.job == job)
        except (Job.DoesNotExist, Application.DoesNotExist):
            return f"⚠️  Vaga #{job_id} não encontrada ou sem rascunho. Rode apply_jobs primeiro."

        stored_answers = app.get_form_data()
        if answers:
            stored_answers.update(answers)

        pending = [k for k, v in stored_answers.items() if v == "__NEEDS_REVIEW__"]
        if pending:
            return (
                f"🚫 Candidatura #{job_id} NÃO submetida — campos de autorização de "
                f"trabalho aguardando sua decisão (país da vaga indefinido):\n"
                + "\n".join(f"  - {k}" for k in pending)
                + f"\nResponda e re-rode: "
                f"`confirm_apply(job_id={job_id}, answers={{\"{pending[0]}\": \"Yes\"}})`"
            )

        # Gera o ref e injeta o alias +ref no campo de email ANTES de preencher, para que
        # a empresa responda em candidaturas+<ref>@gmail.com (conta monitorada).
        ref = secrets.token_urlsafe(4)[:6]
        base_address = _config.get("email", {}).get("address")
        if base_address:
            _inject_email_alias(stored_answers, _build_email_alias(base_address, ref))

        try:
            cv_path = _resolve_cv_path(job.company, _config)
        except CVNotFoundError as e:
            return f"⚠️  {e}\n🚫 Não submeti — não vou subir um CV errado."

        page = await _browser_mod.new_page(_config)
        try:
            await page.goto(job.url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            applier = await _detect_applier(page, _config, _profile)
            if not applier:
                return f"⚠️  ATS não reconhecido para vaga #{job_id}."

            if isinstance(applier, LinkedInApplier):
                await applier.extract_fields()  # opens the modal

            fill_status = await applier.fill_form(stored_answers, cv_path)
            if isinstance(fill_status, dict):
                failed_fields = [k for k, s in fill_status.items() if s.startswith("failed")]
                if failed_fields:
                    _log.warning("confirm_apply #%d: campos com falha no preenchimento: %s", job_id, failed_fields)
            else:
                fill_status = {}
            await _browser_mod.save_screenshot(page, job_id, "03-filled", _config)

            outcome = await applier.submit()
            await _browser_mod.save_screenshot(page, job_id, "04-submitted", _config)
            shot = f"~/.candidatador/screenshots/{job_id}/04-submitted.png"

            if isinstance(outcome, str) and outcome.startswith("failed"):
                # Falha ao submeter (botão não encontrado, erro, ou validação falhou)
                app.status = "draft"
                app.save()
                Job.update(status="reviewed").where(Job.id == job_id).execute()
                fill_summary = (
                    ", ".join(f"{k}={s}" for k, s in fill_status.items() if s != "filled")
                    or "todos preenchidos"
                )
                return (
                    f"⚠️  Candidatura #{job_id} NÃO foi submetida ({outcome}).\n"
                    f"Campos problemáticos: {fill_summary}\n"
                    f"Confira {shot} e rode retry_apply({job_id}) após corrigir."
                )

            if outcome == "unverified":
                # CONSERVADOR: clicou mas não deu para confirmar envio NEM detectar
                # erro de validação. Não marcamos como enviada (evita falso positivo)
                # e não permitimos retry cego (evita duplicar se de fato enviou).
                app.status = "needs_review"
                app.applied_at = None
                app.form_data = json.dumps(stored_answers)
                app.email_ref = ref
                app.updated_at = datetime.now()
                note = (
                    f"[{datetime.now().strftime('%Y-%m-%d')}] submit NÃO confirmado — "
                    f"conferir {shot}. Se foi enviada: update_status({job_id}, 'submitted'). "
                    f"Se NÃO foi: update_status({job_id}, 'draft') e retry_apply({job_id})."
                )
                app.notes = f"{app.notes}\n{note}" if app.notes else note
                app.save()
                Job.update(status="needs_review").where(Job.id == job_id).execute()
                return (
                    f"⚠️  Candidatura #{job_id} ({job.company} / {job.title}): NÃO consegui "
                    f"confirmar o envio.\n"
                    f"🚫 NÃO marquei como enviada e NÃO vou re-submeter sozinho (evita duplicar).\n"
                    f"Confira o screenshot: {shot}\n"
                    f"→ Se foi enviada: `update_status({job_id}, 'submitted')`\n"
                    f"→ Se não foi: `update_status({job_id}, 'draft')` e `retry_apply({job_id})`"
                )

            # outcome == "submitted": confirmado.
            app.status = "submitted"
            app.applied_at = datetime.now()
            app.form_data = json.dumps(stored_answers)
            app.updated_at = datetime.now()
            app.email_ref = ref
            app.save()
            Job.update(status="applied").where(Job.id == job_id).execute()
            _archive_screenshots(job_id, _config)
            return f"✓ Candidatura #{job_id} submetida e confirmada: {job.company} / {job.title}"
        except Exception as e:
            app.status = "draft"
            app.save()
            Job.update(status="reviewed").where(Job.id == job_id).execute()
            return f"⚠️  Erro ao submeter vaga #{job_id}: {e}"
        finally:
            await page.close()


@mcp.tool()
async def retry_apply(job_id: int) -> str:
    """Retry a failed application. Reuses stored draft answers."""
    async with _log_tool("retry_apply"):
        try:
            app = Application.get(Application.job == Job.get_by_id(job_id))
        except (Job.DoesNotExist, Application.DoesNotExist):
            return f"Vaga #{job_id} não tem rascunho salvo. Rode apply_jobs(ids=[{job_id}]) primeiro."
        if app.status == "needs_review":
            return (
                f"🚫 Vaga #{job_id} está em needs_review — pode ter sido enviada. "
                f"NÃO vou re-submeter cegamente (evita candidatura duplicada).\n"
                f"→ Se foi enviada: `update_status({job_id}, 'submitted')`\n"
                f"→ Se não foi: `update_status({job_id}, 'draft')` e então `retry_apply({job_id})`"
            )
        return await confirm_apply(job_id)


@mcp.tool()
async def get_pipeline() -> str:
    """Show full application funnel: counts and list by status."""
    async with _log_tool("get_pipeline"):
        statuses = ["draft", "needs_review", "submitted", "screening", "interviews", "offer", "rejected"]
        lines = ["# Pipeline de Candidaturas\n"]
        for status in statuses:
            apps = list(
                Application.select(Application, Job)
                .join(Job)
                .where(Application.status == status)
                .order_by(Application.updated_at.desc())
            )
            if not apps:
                continue
            lines.append(f"## {status.capitalize()} ({len(apps)})")
            for app in apps:
                date = app.applied_at.strftime("%d/%m") if app.applied_at else "—"
                next_action = f" → {app.next_action}" if app.next_action else ""
                lines.append(f"- #{app.job.id} {app.job.company}/{app.job.title} ({date}){next_action}")
            lines.append("")

        total = Application.select().count()
        lines.append(f"**Total de candidaturas:** {total}")
        return "\n".join(lines)


@mcp.tool()
async def update_status(job_id: int, status: str, notes: str = "", next_action: str = "") -> str:
    """
    Update application status manually.
    status: 'screening' | 'interview' | 'offer' | 'rejected' | 'submitted' | 'draft'
    notes: free text notes appended to history
    next_action: e.g. 'follow up em 2026-06-01'
    """
    async with _log_tool("update_status"):
        valid = {"screening", "interviews", "offer", "rejected", "submitted", "draft"}
        if status not in valid:
            return f"Status inválido. Valores aceitos: {', '.join(sorted(valid))}"
        try:
            job = Job.get_by_id(job_id)
            app = Application.get(Application.job == job)
        except (Job.DoesNotExist, Application.DoesNotExist):
            return f"Vaga #{job_id} não encontrada ou sem candidatura registrada."

        app.status = status
        app.updated_at = datetime.now()
        if notes:
            existing = app.notes or ""
            app.notes = f"{existing}\n[{datetime.now().strftime('%Y-%m-%d')}] {notes}".strip()
        if next_action:
            app.next_action = next_action
        app.save()

        result = f"✓ Vaga #{job_id} ({job.company}/{job.title}): status → {status}"
        if next_action:
            result += f"\n  Próxima ação: {next_action}"
        return result


def _build_email_alias(address: str, ref: str) -> str:
    """'candidaturas@gmail.com' + 'x7k2mp' → 'candidaturas+x7k2mp@gmail.com'"""
    local, _, domain = address.partition("@")
    return f"{local}+{ref}@{domain}"


def _inject_email_alias(answers: dict, alias: str) -> bool:
    """
    Sobrescreve o campo de email do formulário com o alias +ref de rastreamento.
    Procura qualquer label que contenha 'email' ignorando hífen/espaço — assim
    casa tanto 'Email' quanto 'E-mail' (PT). Se não houver, adiciona uma chave
    'Email' como fallback (label mais comum nos ATS).
    Retorna True se algum campo existente foi sobrescrito.
    """
    injected = False
    for key in list(answers.keys()):
        normalized = key.lower().replace("-", "").replace(" ", "")
        if "email" in normalized:
            answers[key] = alias
            injected = True
    if not injected:
        answers["Email"] = alias
    return injected


@mcp.tool()
async def setup_email() -> str:
    """
    Configura autenticação Gmail para candidaturas@gmail.com.
    Rodar apenas uma vez. Abre o browser para autorizar acesso.
    Requer gmail-client.json em ~/.candidatador/.
    """
    async with _log_tool("setup_email"):
        config = load_config()
        email_cfg = config.get("email", {})
        creds_path = os.path.expanduser(email_cfg.get("credentials_path", ""))
        token_path = os.path.expanduser(email_cfg.get("token_path", ""))

        if not os.path.exists(creds_path):
            return (
                f"⚠️  Arquivo de credenciais não encontrado: {creds_path}\n"
                "Baixe o client_secret.json do Google Cloud Console e salve em "
                "~/.candidatador/gmail-client.json"
            )

        try:
            _run_gmail_oauth(creds_path, token_path)
            setup_gmail_service(config)
            return "✓ Autenticação Gmail configurada com sucesso."
        except GmailAuthError as e:
            return f"⚠️  Erro na autenticação Gmail: {e}"
        except Exception as e:
            return f"⚠️  Erro inesperado ao configurar Gmail: {e}"


@mcp.tool()
async def sync_email_responses() -> str:
    """
    Lê emails não lidos em candidaturas@gmail.com,
    classifica com LLM e atualiza o banco de candidaturas.
    Retorna resumo das atualizações feitas.
    """
    async with _log_tool("sync_email_responses"):
        config = load_config()
        updates = await sync_responses(config, _llm_caller)

        if not updates:
            return "Nenhum email novo encontrado."

        lines = [f"# Sync de emails — {len(updates)} atualização(ões)\n"]
        for u in updates:
            company = u.get("company") or "?"
            title = u.get("title") or "?"
            msg_type = u.get("type", "?")
            stage = u.get("stage") or ""
            match_type = u.get("match_type", "")
            stage_str = f" → {stage}" if stage else ""
            lines.append(
                f"- **{company}** / {title}: `{msg_type}`{stage_str} (match: {match_type})"
            )

        return "\n".join(lines)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
