import contextlib
import time as _time
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from candidatador import browser as _browser_mod
from candidatador.config import load_company_list, load_config, load_profile
from candidatador.db import Application, Job, init_db
from candidatador.email_monitor import (
    GmailAuthError,
    _run_gmail_oauth,
    setup_gmail_service,
    sync_responses,
)
from candidatador.llm import make_caller
from candidatador.log import get_logger as _get_logger
from candidatador.log import setup as _setup_logging
from candidatador.services import apply_service, scan_service
from candidatador.startup import validate_startup
from candidatador.views import render_jobs_table

_setup_logging()
_log = _get_logger(__name__)

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
        return await scan_service.scan_and_evaluate(keywords, phase, _config, _profile, _llm_caller)


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
        return await scan_service.add_job(
            url, company, title, description, _config, _profile, _llm_caller
        )


@mcp.tool()
async def list_jobs(status: str = "new", limit: int = 20) -> str:
    """List jobs from DB filtered by status."""
    async with _log_tool("list_jobs"):
        jobs = list(
            Job.select().where(Job.status == status).order_by(Job.score.desc()).limit(limit)
        )
        if not jobs:
            return f"Nenhuma vaga com status='{status}'."
        return render_jobs_table(jobs)


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
            sal = (
                f"${job.salary_min:,}–${job.salary_max:,} {job.salary_currency}"
                if job.salary_max
                else f"${job.salary_min:,}+ {job.salary_currency}"
            )
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
        return await apply_service.apply_jobs(ids, _config, _profile, _llm_caller)


@mcp.tool()
async def confirm_apply(job_id: int, answers: dict | None = None) -> str:
    """
    Submit the application for a job.
    job_id: ID of the job (must have a draft Application in DB)
    answers: optional dict of {field: answer} overrides merged into the saved draft
    """
    async with _log_tool("confirm_apply"):
        return await apply_service.confirm_apply(job_id, answers, _config, _profile)


@mcp.tool()
async def retry_apply(job_id: int) -> str:
    """Retry a failed application. Reuses stored draft answers."""
    async with _log_tool("retry_apply"):
        return await apply_service.retry_apply(job_id, _config, _profile)


@mcp.tool()
async def get_pipeline() -> str:
    """Show full application funnel: counts and list by status."""
    async with _log_tool("get_pipeline"):
        statuses = [
            "draft",
            "needs_review",
            "submitted",
            "screening",
            "interviews",
            "offer",
            "rejected",
        ]
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
                lines.append(
                    f"- #{app.job.id} {app.job.company}/{app.job.title} ({date}){next_action}"
                )
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
        except Job.DoesNotExist, Application.DoesNotExist:
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
        creds_path = str(Path(email_cfg.get("credentials_path", "")).expanduser())
        token_path = str(Path(email_cfg.get("token_path", "")).expanduser())

        if not Path(creds_path).exists():
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
