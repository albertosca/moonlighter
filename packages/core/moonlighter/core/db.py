"""The local SQLite store: its path, its peewee models and their small invariants, and init_db."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Self, override

from peewee import (
    AutoField,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

from moonlighter.core.config.paths import moonlighter_home


def db_path() -> str:
    # Single source of truth for the DB path: explicit override via MOONLIGHTER_DB_PATH,
    # otherwise falls back to moonlighter_home() (respects MOONLIGHTER_HOME).
    return os.environ.get("MOONLIGHTER_DB_PATH") or str(moonlighter_home() / "moonlighter.db")


db = SqliteDatabase(None)  # initialized in init_db()


class BaseModel(Model):
    # peewee's ModelBase metaclass (peewee.py) synthesizes two things on every
    # Model subclass at class-creation time that peewee's own bundled stubs
    # (site-packages/peewee-stubs, vendored since peewee 4.1.1) don't declare:
    # an implicit `id` AutoField primary key when no field declares
    # primary_key=True, and a per-subclass `DoesNotExist` exception class. The
    # stubs do declare Model's own `get_or_create` classmethod, but untyped.
    # Before the stubs existed, `peewee.Model` resolved to `Any` (via this
    # project's `ignore_missing_imports` fallback for `peewee.*`), so every one
    # of these was silently Any-typed too.
    #
    # `id` is declared for real: this is exactly what peewee already synthesizes
    # for a model with no explicit primary key (see ModelBase.__new__), so it's
    # behaviorally a no-op -- it only spells out, for the type checker, what was
    # already happening at runtime. `DoesNotExist` and `get_or_create` are
    # declared under TYPE_CHECKING only: real assignments would fight the
    # metaclass's `DoesNotExist` and replace peewee's own `get_or_create`.
    id = AutoField()

    if TYPE_CHECKING:
        DoesNotExist: ClassVar[type[Exception]]

        @classmethod
        @override
        def get_or_create(model_class, **lookups: Any) -> tuple[Self, bool]: ...

    class Meta:
        database = db


class Job(BaseModel):
    source = CharField()
    company = CharField()
    title = CharField()
    url = CharField(unique=True)
    location = CharField(null=True)
    remote_type = CharField(null=True)  # 'remote' | 'hybrid' | 'onsite'
    description = TextField(null=True)
    posted_at = DateTimeField(null=True)
    score = FloatField(null=True)
    score_notes = TextField(null=True)
    caveats = TextField(null=True)  # JSON array string
    salary_min = IntegerField(null=True)
    salary_max = IntegerField(null=True)
    salary_currency = CharField(null=True)
    salary_source = CharField(null=True)  # 'stated' | 'llm_estimate' | 'third_party'
    salary_notes = TextField(null=True)
    # 'new'|'reviewed'|'applying'|'needs_review'|'applied'|'rejected'|'archived'
    # (closed_at set = was live, gone from source)
    status = CharField(default="new")
    found_at = DateTimeField(default=datetime.now)
    closed_at = DateTimeField(null=True)

    def get_caveats(self) -> list[str]:
        return json.loads(self.caveats) if self.caveats else []


class Application(BaseModel):
    job = ForeignKeyField(Job, backref="applications")
    applied_at = DateTimeField(null=True)
    form_data = TextField(null=True)  # JSON dict: field_name -> answer
    notes = TextField(null=True)
    # 'draft'|'filled'|'submitted'|'needs_review'|'screening'|'interviews'|'offer'|'rejected'
    status = CharField(default="draft")
    next_action = TextField(null=True)
    updated_at = DateTimeField(default=datetime.now)
    email_ref = CharField(max_length=8, null=True, unique=True)
    current_stage = CharField(null=True)

    def get_form_data(self) -> dict[str, Any]:
        return json.loads(self.form_data) if self.form_data else {}


class ScanLog(BaseModel):
    job_url = CharField(unique=True)
    scanned_at = DateTimeField(default=datetime.now)
    source = CharField()


class ProcessedEmail(BaseModel):
    """Local dedup of emails already processed by the sync.

    With it, the monitor doesn't need to mark the email in Gmail (keeps the
    autonomous sync 100% read-only).
    """

    message_id = CharField(unique=True)
    processed_at = DateTimeField(default=datetime.now)


class AnswerBankEntry(BaseModel):
    """Cross-job cache of approved LLM answers, keyed by normalised question text.

    Populated by moonlighter.application.answers.bank.store.promote_application
    when an Application is marked "submitted" — see
    moonlighter.application.answers.bank.eligibility for the normalisation and
    kind-eligibility rules. `kind` is stored for visibility and debugging only;
    it is not consulted on read (the label was already kind-checked before the
    row was written).
    """

    normalized_question = CharField(unique=True)
    kind = CharField()
    answer = TextField()
    source_job_id = IntegerField()
    updated_at = DateTimeField(default=datetime.now)


class CVBootstrapDecline(BaseModel):
    """One row means the CV-pool bootstrap offer was declined once and must never be offered again.

    Existence-as-flag, the same idiom ensure_tailored_cv already uses for "is
    the feature on" (a file exists or it doesn't). One installation needs at
    most one row; a second record_cv_bootstrap_decline() call is a harmless
    no-op, not an error.
    """

    declined_at = DateTimeField(default=datetime.now)


def cv_bootstrap_declined() -> bool:
    return CVBootstrapDecline.select().exists()


def record_cv_bootstrap_decline() -> None:
    if not cv_bootstrap_declined():
        CVBootstrapDecline.create()


_APP_TO_JOB_STATUS = {
    "submitted": "applied",
    "screening": "applied",
    "interviews": "applied",
    "offer": "applied",
    "rejected": "rejected",
}


def sync_job_status(application: Application) -> None:
    """Pulls Job.status along whenever Application.status changes.

    Provenance: 2026-08-21 manual triage — 5 jobs still 'new' while their
    Application was already submitted/rejected, nearly offering a duplicate
    application twice in one session. Every Application.status writer calls
    this after saving; 'draft' maps to nothing (a draft is not yet an
    application the queue should hide).
    """
    target = _APP_TO_JOB_STATUS.get(str(application.status))
    if target is None:
        return
    job = application.job
    if job.status != target:
        job.status = target
        job.save()


def init_db() -> None:
    path = db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db.init(path)
    db.connect(reuse_if_open=True)
    db.create_tables(
        [Job, Application, ScanLog, ProcessedEmail, AnswerBankEntry, CVBootstrapDecline],
        safe=True,
    )
    from moonlighter.core.migrations import run_migrations  # noqa: PLC0415 - migrations calls get_logger() at import, which configures logging; keep that out of import moonlighter.core.db

    run_migrations(db)
