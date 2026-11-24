"""The shape of a loaded config.yaml, for mypy: a TypedDict per block, a plain dict at runtime.

The runtime check lives in validation._CONFIG_SCHEMA; tests/core/config/test_model_agreement.py
fails when the two disagree. Element types inside lists and dicts (list[str],
dict[str, str]) are what the YAML author promises: the runtime check stops at the container.
"""

from typing import NotRequired, TypedDict


class CvConfig(TypedDict):
    """The cv: block. pool, template_dir and generated_dir switch on the tailored CV."""

    default: str
    by_company: dict[str, str]
    pool: NotRequired[str]
    template_dir: NotRequired[str]
    generated_dir: NotRequired[str]


class WorkAuthorizationConfig(TypedDict):
    """The work_authorization: block."""

    citizenship_country: str
    authorized_answer: str
    not_authorized_answer: str


class EmailConfig(TypedDict):
    """The email: block. Only the two file paths have defaults."""

    credentials_path: str
    token_path: str
    address: NotRequired[str]
    processed_label: NotRequired[str]
    mark_processed: NotRequired[bool]
    archive_ref_matched: NotRequired[bool]
    archive_all_classified: NotRequired[bool]
    lookback_days: NotRequired[int]
    interview_stages: NotRequired[list[str]]


class DefaultsConfig(TypedDict):
    """Every key DEFAULTS holds. A number the schema takes as int or float is float."""

    browser_path: str
    llm_backend: str
    llm_timeout_seconds: float
    score_threshold: float
    answer_bank_max_age_days: int | None
    llm_model: str
    eval_model: str
    slow_mo_ms: int
    title_blocklist: list[str]
    scan_concurrency: int
    scan_batch_size: int
    cv: CvConfig
    work_authorization: WorkAuthorizationConfig
    email: EmailConfig
    portal_max_age_days: int
    no_response_after_days: int
    email_sync_max_age_days: int


class Config(DefaultsConfig):
    """A loaded, validated config: the defaults, the two load-time paths, the optional keys."""

    browser_session_dir: str
    screenshots_dir: str
    brave_path: NotRequired[str]
    cursor_model: NotRequired[str]
    scan_gupy: NotRequired[bool]
    scan_remoteok: NotRequired[bool]
    scan_remotive: NotRequired[bool]
    remotive_category: NotRequired[str]
    scan_wwr: NotRequired[bool]
    wwr_category: NotRequired[str]
    scan_hn_whoishiring: NotRequired[bool]
