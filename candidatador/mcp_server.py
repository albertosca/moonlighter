import contextlib
import json
import os
import secrets
import shutil
import time as _time
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from candidatador import browser as _browser_mod
from candidatador.applicator.ashby import AshbyApplier
from candidatador.applicator.base import generate_answers
from candidatador.applicator.cv import CVNotFoundError, resolve_cv_path
from candidatador.applicator.email_alias import build_email_alias, inject_email_alias
from candidatador.applicator.greenhouse import GreenhouseApplier
from candidatador.applicator.lever import LeverApplier
from candidatador.applicator.linkedin import LinkedInApplier
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
from candidatador.services import scan_service
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

                if isinstance(applier, LinkedInApplier) and not await applier.is_easy_apply():
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
                    job=job, defaults={"status": "draft", "form_data": json.dumps(draft.answers)}
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
                        f'`confirm_apply(job_id={job_id}, answers={{"<campo>": "Yes/No"}})`'
                    )
                for field, answer in draft.answers.items():
                    if answer == "__NEEDS_REVIEW__":
                        continue
                    lines.append(f"\n**{field}**\n{answer}")
                lines.append(f"\nPara aprovar e candidatar: `confirm_apply(job_id={job_id})`")
                lines.append(
                    'Para editar: passe `answers={"campo": "nova resposta"}` no confirm_apply'
                )
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
        except Job.DoesNotExist, Application.DoesNotExist:
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
                f'`confirm_apply(job_id={job_id}, answers={{"{pending[0]}": "Yes"}})`'
            )

        # Gera o ref e injeta o alias +ref no campo de email ANTES de preencher, para que
        # a empresa responda em candidaturas+<ref>@gmail.com (conta monitorada).
        ref = secrets.token_urlsafe(4)[:6]
        base_address = _config.get("email", {}).get("address")
        if base_address:
            inject_email_alias(stored_answers, build_email_alias(base_address, ref))

        try:
            cv_path = resolve_cv_path(job.company, _config)
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
                    _log.warning(
                        "confirm_apply #%d: campos com falha no preenchimento: %s",
                        job_id,
                        failed_fields,
                    )
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
        except Job.DoesNotExist, Application.DoesNotExist:
            return (
                f"Vaga #{job_id} não tem rascunho salvo. Rode apply_jobs(ids=[{job_id}]) primeiro."
            )
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
