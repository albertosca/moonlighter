"""Where the tailored-CV feature keeps its files.

The pool, the templates and each job's generated documents. Every location is resolved from the config at call time, under the operator's
home, so a test or a second profile that changes the home is honoured. This
module imports nothing else from the package, which keeps it safe for anything
that only needs a path (the doctor's link check, the answer layer's CV lookup).
"""

from pathlib import Path
from typing import Any

from moonlighter.core.config.paths import resolve_under_home


def generated_dir_for(config: dict[str, Any], job_id: int) -> Path:
    base = (config.get("cv") or {}).get("generated_dir")
    root = resolve_under_home(base) if base else resolve_under_home("cv-generated")
    return root / str(job_id)


# Conventional defaults used whenever cv.pool/cv.template_dir is absent from
# config -- the feature still turns on purely by the file existing (opt-in
# by existence, unchanged), it just has somewhere to exist without the user
# hand-writing the config key first. Only the bootstrap (cvgen/bootstrap.py)
# ever writes here; nothing conjures a file at this path on its own.
_DEFAULT_POOL_NAME = "cv-pool.yaml"
_DEFAULT_TEMPLATE_DIR_NAME = "cv-templates"


# KNOWN LIMITATION (found by review, 2026-09-21; ruled: park, not fix): an
# `or` fallback cannot distinguish cv.pool being ABSENT from cv.pool being
# explicitly set to null/"" -- both fall through to the default path below.
# A coincidental file at that default path would then override an explicit
# `cv: {pool: null}`. Not fixed because no config in this project (not
# config.example.yaml, not DEFAULTS) ever sets cv.pool at all, let alone
# explicitly nulls it -- simply omitting the key already means "off," so
# there is no realistic config that hits this path -- and a correct fix
# needs Path | None through every caller, which is real design surface the
# original brainstorm never covered. Revisit if a real config ever needs to
# explicitly null cv.pool.
def resolved_pool_path(config: dict[str, Any]) -> Path:
    pool_path = (config.get("cv") or {}).get("pool") or _DEFAULT_POOL_NAME
    return resolve_under_home(pool_path)


def resolved_template_dir(config: dict[str, Any]) -> Path:
    template_directory = (config.get("cv") or {}).get("template_dir") or _DEFAULT_TEMPLATE_DIR_NAME
    return resolve_under_home(template_directory)
