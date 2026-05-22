import asyncio
import json
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from peewee import IntegrityError
from rich.table import Table
from rich.console import Console
from rich import box
import io

from candidatador.db import init_db, Job, ScanLog
from candidatador.config import load_config, load_profile, load_company_list
from candidatador.scanner.http_sources import GreenhouseScanner, LeverScanner, AshbyScanner
from candidatador.evaluator import evaluate_job

mcp = FastMCP("candidatador")
_config = load_config()
try:
    _profile = load_profile()
except FileNotFoundError:
    print("⚠️  profile/profile.yaml não encontrado — usando perfil vazio. Crie o arquivo para avaliações melhores.")
    _profile = {}
_companies = load_company_list()
init_db()

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

    # Dedup against scan_log
    seen_urls = {row.job_url for row in ScanLog.select(ScanLog.job_url)}
    new_raw = [j for j in all_raw if j.url not in seen_urls]

    if not new_raw:
        return "Nenhuma vaga nova encontrada."

    # Evaluate each new job with LLM
    results = []
    for raw in new_raw:
        eval_result = await evaluate_job(
            company=raw.company,
            title=raw.title,
            description=raw.description or f"{raw.title} at {raw.company}",
            profile=_profile,
            model=model,
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
            results.append(job)
        except IntegrityError:
            pass  # URL already in DB, skip

    above = [j for j in results if j.status == "new"]
    below = len(results) - len(above)

    if not above:
        return f"{len(results)} vagas processadas. Nenhuma passou o threshold de {threshold}."

    table = _render_table(above)
    footer = f"\n∗ = salário estimado pelo LLM  |  {below} vagas abaixo do threshold arquivadas"
    return f"{len(results)} vagas novas processadas. {len(above)} acima do threshold:\n\n{table}{footer}"


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
    lines = [
        f"# {job.company} — {job.title}",
        f"**Source:** {job.source}  |  **Status:** {job.status}",
        f"**Score:** {job.score:.1f}/10  |  **Remoto:** {job.remote_type or 'n/d'}",
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


def main():
    mcp.run()
