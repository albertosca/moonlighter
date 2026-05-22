import datetime
import json
import os
from peewee import (
    SqliteDatabase, Model, CharField, TextField, FloatField,
    IntegerField, DateTimeField, ForeignKeyField
)


def _db_path() -> str:
    return os.environ.get(
        "CANDIDATADOR_DB_PATH",
        os.path.expanduser("~/.candidatador/candidatador.db")
    )


db = SqliteDatabase(None)  # initialized in init_db()


class BaseModel(Model):
    class Meta:
        database = db


class Job(BaseModel):
    source = CharField()
    company = CharField()
    title = CharField()
    url = CharField(unique=True)
    location = CharField(null=True)
    remote_type = CharField(null=True)   # 'remote' | 'hybrid' | 'onsite'
    description = TextField(null=True)
    posted_at = DateTimeField(null=True)
    score = FloatField(null=True)
    score_notes = TextField(null=True)
    caveats = TextField(null=True)       # JSON array string
    salary_min = IntegerField(null=True)
    salary_max = IntegerField(null=True)
    salary_currency = CharField(null=True)
    salary_source = CharField(null=True) # 'stated' | 'llm_estimate' | 'third_party'
    salary_notes = TextField(null=True)
    status = CharField(default="new")    # 'new'|'reviewed'|'applying'|'applied'|'rejected'|'archived'
    found_at = DateTimeField(default=datetime.datetime.now)

    def get_caveats(self) -> list[str]:
        return json.loads(self.caveats) if self.caveats else []


class Application(BaseModel):
    job = ForeignKeyField(Job, backref="applications")
    applied_at = DateTimeField(null=True)
    form_data = TextField(null=True)     # JSON dict: field_name -> answer
    notes = TextField(null=True)
    status = CharField(default="draft")  # 'draft'|'submitted'|'screening'|'interview'|'offer'|'rejected'
    next_action = TextField(null=True)
    updated_at = DateTimeField(default=datetime.datetime.now)

    def get_form_data(self) -> dict:
        return json.loads(self.form_data) if self.form_data else {}


class ScanLog(BaseModel):
    job_url = CharField(unique=True)
    scanned_at = DateTimeField(default=datetime.datetime.now)
    source = CharField()


def init_db():
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db.init(path)
    db.connect(reuse_if_open=True)
    db.create_tables([Job, Application, ScanLog], safe=True)
