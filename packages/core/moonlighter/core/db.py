import datetime
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Self

from moonlighter.core.config import moonlighter_home
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


def _db_path() -> str:
    # Single source of truth for the DB path: explicit override via MOONLIGHTER_DB_PATH,
    # otherwise falls back to moonlighter_home() (respects MOONLIGHTER_HOME).
    return os.environ.get("MOONLIGHTER_DB_PATH") or str(moonlighter_home() / "moonlighter.db")


db = SqliteDatabase(None)  # initialized in init_db()


class BaseModel(Model):
    # peewee's ModelBase metaclass (peewee.py) synthesizes three things on every
    # Model subclass at class-creation time, none of which peewee's own bundled
    # stubs (site-packages/peewee-stubs, vendored since peewee 4.1.1) know about:
    # an implicit `id` AutoField primary key when no field declares
    # primary_key=True, a per-subclass `DoesNotExist` exception class, and an
    # untyped `get_or_create` classmethod. Before the stubs existed, `peewee.Model`
    # resolved to `Any` (via this project's `ignore_missing_imports` fallback for
    # `peewee.*`), so every one of these was silently Any-typed too.
    #
    # `id` is declared for real: this is exactly what peewee already synthesizes
    # for a model with no explicit primary key (see ModelBase.__new__), so it's
    # behaviorally a no-op -- it only spells out, for the type checker, what was
    # already happening at runtime. `DoesNotExist` and `get_or_create` are
    # declared under TYPE_CHECKING only, since real assignments here would fight
    # the ones peewee's metaclass makes on every subclass.
    id = AutoField()

    if TYPE_CHECKING:
        DoesNotExist: ClassVar[type[Exception]]

        @classmethod
        def get_or_create(cls, **kwargs: Any) -> tuple[Self, bool]: ...

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
    status = CharField(
        default="new"
    )  # 'new'|'reviewed'|'applying'|'needs_review'|'applied'|'rejected'|'archived'|'closed'
    found_at = DateTimeField(default=datetime.datetime.now)
    closed_at = DateTimeField(null=True)

    def get_caveats(self) -> list[str]:
        return json.loads(self.caveats) if self.caveats else []


class Application(BaseModel):
    job = ForeignKeyField(Job, backref="applications")
    applied_at = DateTimeField(null=True)
    form_data = TextField(null=True)  # JSON dict: field_name -> answer
    notes = TextField(null=True)
    status = CharField(
        default="draft"
    )  # 'draft'|'filled'|'submitted'|'needs_review'|'screening'|'interviews'|'offer'|'rejected'
    next_action = TextField(null=True)
    updated_at = DateTimeField(default=datetime.datetime.now)
    email_ref = CharField(max_length=8, null=True, unique=True)
    current_stage = CharField(null=True)

    def get_form_data(self) -> dict[str, Any]:
        return json.loads(self.form_data) if self.form_data else {}


class ScanLog(BaseModel):
    job_url = CharField(unique=True)
    scanned_at = DateTimeField(default=datetime.datetime.now)
    source = CharField()


class ProcessedEmail(BaseModel):
    """Local dedup of emails already processed by the sync, so the monitor doesn't
    need to mark the email in Gmail (keeps the autonomous sync 100% read-only)."""

    message_id = CharField(unique=True)
    processed_at = DateTimeField(default=datetime.datetime.now)


def init_db() -> None:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db.init(path)
    db.connect(reuse_if_open=True)
    db.create_tables([Job, Application, ScanLog, ProcessedEmail], safe=True)
    from moonlighter.core.migrations import run_migrations

    run_migrations(db)
