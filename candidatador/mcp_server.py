import asyncio
import json
import secrets
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from peewee import IntegrityError
from rich.table import Table
from rich.console import Console
from rich import box
import io

from candidatador.db import init_db, Job, ScanLog, Application
from candidatador.config import load_config, load_profile, load_company_list
from candidatador.scanner.http_sources import GreenhouseScanner, LeverScanner, AshbyScanner
from candidatador.evaluator import evaluate_job
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

mcp = FastMCP("candidatador")
_config = load_config()
try:
    _profile = load_profile()
except FileNotFoundError:
    _profile = {}
_companies = load_company_list()
init_db()
_llm_caller = make_caller(_config)

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
async def scan_and_evaluate(keywords: str = "") -> str:
    """Scan all configured job boards, evaluate with LLM, return new jobs above threshold."""
    threshold = _config["score_threshold"]
    model = _config["llm_model"]

    # Fetch raw jobs from HTTP sources
    scanners = {
        "greenhouse": GreenhouseScanner(),
        "lever": LeverScanner(),
        "ashby": AshbyScanner(),
    }
    all_raw = []
    for source, scanner in scanners.items():
        slugs = _companies.get(source, [])
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

    async def _eval_and_save(raw) -> Job | None:
        eval_result = await evaluate_job(
            company=raw.company,
            title=raw.title,
            description=raw.description or f"{raw.title} at {raw.company}",
            profile=_profile,
            model=model,
            _caller=_llm_caller,
        )
        try:
            job = Job.create(
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
            ScanLog.create(job_url=raw.url, source=raw.source)
            return job
        except IntegrityError:
            return None

    for i in range(0, len(new_raw), BATCH_SIZE):
        batch = new_raw[i:i + BATCH_SIZE]
        batch_results = await asyncio.gather(*[_eval_and_save(raw) for raw in batch])
        results.extend([j for j in batch_results if j is not None])

    above = [j for j in results if j.status == "new"]
    below = len(results) - len(above)

    if not above:
        return _with_li_warning(f"{len(results)} vagas processadas. Nenhuma passou o threshold de {threshold}.")

    table = _render_table(above)
    footer = f"\n∗ = salário estimado pelo LLM  |  {below} vagas abaixo do threshold arquivadas"
    return _with_li_warning(f"{len(results)} vagas novas processadas. {len(above)} acima do threshold:\n\n{table}{footer}")


@mcp.tool()
async def list_jobs(status: str = "new", limit: int = 20) -> str:
    """List jobs from DB filtered by status."""
    jobs = list(Job.select().where(Job.status == status).order_by(Job.score.desc()).limit(limit))
    if not jobs:
        return f"Nenhuma vaga com status='{status}'."
    return _render_table(jobs)


@mcp.tool()
async def get_job(id: int) -> str:
    """Get full details of a job posting."""
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
            for field, answer in draft.answers.items():
                lines.append(f"\n**{field}**\n{answer}")
            lines.append(f"\nPara aprovar e candidatar: `confirm_apply(job_id={job_id})`")
            lines.append(f"Para editar: passe `answers={{\"campo\": \"nova resposta\"}}` no confirm_apply")
            drafts_output.append("\n".join(lines))

        except Exception as e:
            drafts_output.append(f"⚠️  Vaga #{job_id}: erro — {e}")
        finally:
            await page.close()

    return "\n\n---\n".join(drafts_output)


@mcp.tool()
async def confirm_apply(job_id: int, answers: dict | None = None) -> str:
    """
    Submit the application for a job.
    job_id: ID of the job (must have a draft Application in DB)
    answers: optional dict of {field: answer} overrides merged into the saved draft
    """
    try:
        job = Job.get_by_id(job_id)
        app = Application.get(Application.job == job)
    except (Job.DoesNotExist, Application.DoesNotExist):
        return f"⚠️  Vaga #{job_id} não encontrada ou sem rascunho. Rode apply_jobs primeiro."

    stored_answers = app.get_form_data()
    if answers:
        stored_answers.update(answers)

    # Gera o ref e injeta o alias +ref no campo de email ANTES de preencher, para que
    # a empresa responda em candidaturas+<ref>@gmail.com (conta monitorada).
    ref = secrets.token_urlsafe(4)[:6]
    base_address = _config.get("email", {}).get("address")
    if base_address:
        _inject_email_alias(stored_answers, _build_email_alias(base_address, ref))

    cv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile", "cv.pdf")
    if not os.path.exists(cv_path):
        return f"⚠️  CV não encontrado em {cv_path}. Coloque seu CV em profile/cv.pdf."

    page = await _browser_mod.new_page(_config)
    try:
        await page.goto(job.url, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)

        applier = await _detect_applier(page, _config, _profile)
        if not applier:
            return f"⚠️  ATS não reconhecido para vaga #{job_id}."

        if isinstance(applier, LinkedInApplier):
            await applier.extract_fields()  # opens the modal

        await applier.fill_form(stored_answers, cv_path)
        await _browser_mod.save_screenshot(page, job_id, "03-filled", _config)

        outcome = await applier.submit()
        await _browser_mod.save_screenshot(page, job_id, "04-submitted", _config)
        shot = f"~/.candidatador/screenshots/{job_id}/04-submitted.png"

        if outcome == "failed":
            # Nem conseguiu clicar em enviar — seguro re-tentar.
            app.status = "draft"
            app.save()
            Job.update(status="reviewed").where(Job.id == job_id).execute()
            return (
                f"⚠️  Não consegui submeter a vaga #{job_id} (botão não encontrado ou erro). "
                f"Confira {shot} e rode retry_apply({job_id}) se quiser tentar de novo."
            )

        # outcome == "submitted" ou "unverified": em ambos o clique ocorreu, então
        # tratamos como ENVIADA e NÃO re-submetemos (evita candidatura duplicada).
        app.status = "submitted"
        app.applied_at = datetime.now()
        app.form_data = json.dumps(stored_answers)
        app.updated_at = datetime.now()
        app.email_ref = ref
        if outcome == "unverified":
            note = f"[{datetime.now().strftime('%Y-%m-%d')}] enviada sem confirmação automática — verificar manualmente"
            app.notes = f"{app.notes}\n{note}" if app.notes else note
        app.save()
        Job.update(status="applied").where(Job.id == job_id).execute()

        if outcome == "submitted":
            return f"✓ Candidatura #{job_id} submetida e confirmada: {job.company} / {job.title}"
        return (
            f"⚠️  Candidatura #{job_id} ({job.company} / {job.title}) foi ENVIADA, mas não consegui "
            f"confirmar o sucesso automaticamente.\n"
            f"Confira na mão o screenshot: {shot}\n"
            f"🚫 NÃO rode retry_apply — registrei como enviada para evitar candidatura duplicada."
        )
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
    try:
        Application.get(Application.job == Job.get_by_id(job_id))
    except (Job.DoesNotExist, Application.DoesNotExist):
        return f"Vaga #{job_id} não tem rascunho salvo. Rode apply_jobs(ids=[{job_id}]) primeiro."
    return await confirm_apply(job_id)


@mcp.tool()
async def get_pipeline() -> str:
    """Show full application funnel: counts and list by status."""
    statuses = ["draft", "submitted", "screening", "interviews", "offer", "rejected"]
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
    Procura qualquer label contendo 'email' (case-insensitive). Se não houver,
    adiciona uma chave 'Email' como fallback (label mais comum nos ATS).
    Retorna True se algum campo existente foi sobrescrito.
    """
    injected = False
    for key in list(answers.keys()):
        if "email" in key.lower():
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
