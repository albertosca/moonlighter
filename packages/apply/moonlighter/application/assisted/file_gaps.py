"""The gap a file question becomes, naming the CV to attach when the label asks for one."""

import re
from pathlib import Path
from typing import Any

from moonlighter.application.answers.cv import CVNotFoundError, resolve_cv_path
from moonlighter.application.assisted.questions import FormQuestion

# File fields whose label asks for a CV/resume — the only ones whose gap should
# name the configured CV as the file to attach.
_CV_LABEL = re.compile(r"\bcv\b|resume|curr[ií]c", re.IGNORECASE)


def file_gap_reason(question: FormQuestion, config: dict[str, Any], job: dict[str, Any]) -> str:
    """Why a file question is always a gap, and which file to attach when that is knowable."""
    # A file cannot be pasted, but naming the exact file to attach turns a
    # dead end into an instruction — only for CV-shaped labels: a "Cover
    # letter" gap naming the CV instructs the operator to attach the
    # wrong document (found on the GitLab gate sheet, 2026-08-13).
    if _CV_LABEL.search(question.label):
        # Local import, same cycle-avoidance as answers/cv.py's resolve_cv_path:
        # answers/assisted must not import cvgen at module level.
        from moonlighter.application.cvgen.service import (  # noqa: PLC0415 - answers/assisted must not import cvgen at module level
            generated_dir_for,
        )

        try:
            path = resolve_cv_path(str(job.get("company") or ""), config, job_id=job.get("id"))
            reason = f"upload this file yourself: {path}"
            tailored_root = generated_dir_for(config, int(job["id"])) if job.get("id") else None
            if tailored_root and Path(path).is_relative_to(tailored_root):
                reason += " (tailored for this job — review it before uploading)"
        except CVNotFoundError:
            reason = "upload a file yourself — no CV is configured"
    else:
        reason = "upload a file yourself"
    return reason
