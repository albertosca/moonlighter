"""Serviço de candidatura: detecta o ATS, gera rascunho (apply_jobs), submete
(confirm_apply) e re-tenta (retry_apply).

As tools MCP em mcp_server são wrappers finos que chamam estas funções passando
config/profile/caller. A lógica fica aqui, testável isolada.
"""

import json
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from candidatador import browser
from candidatador.applicator.ashby import AshbyApplier
from candidatador.applicator.base import BaseApplier, generate_answers
from candidatador.applicator.cv import CVNotFoundError, resolve_cv_path
from candidatador.applicator.email_alias import build_email_alias, inject_email_alias
from candidatador.applicator.greenhouse import GreenhouseApplier
from candidatador.applicator.lever import LeverApplier
from candidatador.applicator.linkedin import LinkedInApplier
from candidatador.db import Application, Job
from candidatador.llm import LLMCaller
from candidatador.log import get_logger

logger = get_logger(__name__)

_APPLIER_CLASSES = [LinkedInApplier, GreenhouseApplier, LeverApplier, AshbyApplier]


async def detect_applier(
    page: Page, config: dict[str, Any], profile: dict[str, Any]
) -> BaseApplier | None:
    for cls in _APPLIER_CLASSES:
        applier = cls(page, config, profile)  # type: ignore[abstract]
        if await applier.detect():
            return applier
    return None


def archive_screenshots(job_id: int, config: dict[str, Any]) -> None:
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
        logger.info("archive_screenshots: #%d → done/", job_id)
    except Exception as e:
        logger.debug("archive_screenshots: falha (não crítico) — %s", e)


async def apply_jobs(
    ids: list[int], config: dict[str, Any], profile: dict[str, Any], caller: LLMCaller
) -> str:
    drafts_output = []
    for job_id in ids:
        try:
            job = Job.get_by_id(job_id)
        except Job.DoesNotExist:
            drafts_output.append(f"⚠️  Vaga #{job_id} não encontrada.")
            continue

        page = await browser.new_page(config)
        try:
            await page.goto(job.url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            await browser.save_screenshot(page, job_id, "01-job-page", config)

            applier = await detect_applier(page, config, profile)
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
            await browser.save_screenshot(page, job_id, "02-form", config)

            draft = await generate_answers(
                company=job.company,
                title=job.title,
                description=job.description or "",
                fields=fields,
                profile=profile,
                model=config["llm_model"],
                job_id=job_id,
                _caller=caller,
                config=config,
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
            lines.append('Para editar: passe `answers={"campo": "nova resposta"}` no confirm_apply')
            drafts_output.append("\n".join(lines))

        except Exception as e:
            drafts_output.append(f"⚠️  Vaga #{job_id}: erro — {e}")
        finally:
            await page.close()

    return "\n\n---\n".join(drafts_output)


async def confirm_apply(
    job_id: int, answers: dict[str, str] | None, config: dict[str, Any], profile: dict[str, Any]
) -> str:
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
    base_address = config.get("email", {}).get("address")
    if base_address:
        inject_email_alias(stored_answers, build_email_alias(base_address, ref))

    try:
        cv_path = resolve_cv_path(job.company, config)
    except CVNotFoundError as e:
        return f"⚠️  {e}\n🚫 Não submeti — não vou subir um CV errado."

    page = await browser.new_page(config)
    try:
        await page.goto(job.url, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)

        applier = await detect_applier(page, config, profile)
        if not applier:
            return f"⚠️  ATS não reconhecido para vaga #{job_id}."

        if isinstance(applier, LinkedInApplier):
            await applier.extract_fields()  # opens the modal

        fill_status = await applier.fill_form(stored_answers, cv_path)
        if isinstance(fill_status, dict):
            failed_fields = [k for k, s in fill_status.items() if s.startswith("failed")]
            if failed_fields:
                logger.warning(
                    "confirm_apply #%d: campos com falha no preenchimento: %s",
                    job_id,
                    failed_fields,
                )
        else:
            fill_status = {}
        await browser.save_screenshot(page, job_id, "03-filled", config)

        outcome = await applier.submit()
        await browser.save_screenshot(page, job_id, "04-submitted", config)
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
        archive_screenshots(job_id, config)
        return f"✓ Candidatura #{job_id} submetida e confirmada: {job.company} / {job.title}"
    except Exception as e:
        app.status = "draft"
        app.save()
        Job.update(status="reviewed").where(Job.id == job_id).execute()
        return f"⚠️  Erro ao submeter vaga #{job_id}: {e}"
    finally:
        await page.close()


async def retry_apply(job_id: int, config: dict[str, Any], profile: dict[str, Any]) -> str:
    try:
        app = Application.get(Application.job == Job.get_by_id(job_id))
    except Job.DoesNotExist, Application.DoesNotExist:
        return f"Vaga #{job_id} não tem rascunho salvo. Rode apply_jobs(ids=[{job_id}]) primeiro."
    if app.status == "needs_review":
        return (
            f"🚫 Vaga #{job_id} está em needs_review — pode ter sido enviada. "
            f"NÃO vou re-submeter cegamente (evita candidatura duplicada).\n"
            f"→ Se foi enviada: `update_status({job_id}, 'submitted')`\n"
            f"→ Se não foi: `update_status({job_id}, 'draft')` e então `retry_apply({job_id})`"
        )
    return await confirm_apply(job_id, None, config, profile)
