import datetime
import json
import os
from pathlib import Path
from typing import Any

from candidatador.core.config import candidatador_home
from peewee import (
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
    # Fonte única do caminho do banco: override explícito via CANDIDATADOR_DB_PATH,
    # senão segue candidatador_home() (respeita CANDIDATADOR_HOME).
    return os.environ.get("CANDIDATADOR_DB_PATH") or str(candidatador_home() / "candidatador.db")


db = SqliteDatabase(None)  # initialized in init_db()


class BaseModel(Model):  # type: ignore[misc]  # peewee.Model é untyped (Any)
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
    status = CharField(default="new")  # 'new'|'reviewed'|'applying'|'applied'|'rejected'|'archived'
    found_at = DateTimeField(default=datetime.datetime.now)

    def get_caveats(self) -> list[str]:
        return json.loads(self.caveats) if self.caveats else []


class Application(BaseModel):
    job = ForeignKeyField(Job, backref="applications")
    applied_at = DateTimeField(null=True)
    form_data = TextField(null=True)  # JSON dict: field_name -> answer
    notes = TextField(null=True)
    status = CharField(
        default="draft"
    )  # 'draft'|'submitted'|'screening'|'interviews'|'offer'|'rejected'
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
    """Dedup local de emails já processados pelo sync, para que o monitor não
    precise marcar o email no Gmail (mantém o sync autônomo 100% leitura)."""

    message_id = CharField(unique=True)
    processed_at = DateTimeField(default=datetime.datetime.now)


def init_db() -> None:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db.init(path)
    db.connect(reuse_if_open=True)
    db.create_tables([Job, Application, ScanLog, ProcessedEmail], safe=True)
    # Migration segura: adiciona colunas novas se ainda não existem
    cursor = db.execute_sql("PRAGMA table_info(application)")
    existing = {row[1] for row in cursor.fetchall()}
    if "email_ref" not in existing:
        db.execute_sql("ALTER TABLE application ADD COLUMN email_ref VARCHAR(8) NULL")
        db.execute_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS application_email_ref "
            "ON application (email_ref) WHERE email_ref IS NOT NULL"
        )
    if "current_stage" not in existing:
        db.execute_sql("ALTER TABLE application ADD COLUMN current_stage VARCHAR(255) NULL")
