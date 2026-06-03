"""
Tests for candidatador.email_monitor

Cobertura:
  - extract_ref: pura, sem mocks
  - classify_response: mock llm_caller
  - parse_message: mock Gmail service
  - fetch_unread_messages: mock Gmail service
  - mark_processed: mock Gmail service
  - setup_gmail_service: mock google.oauth2 + googleapiclient
  - sync_responses: mock Gmail + tmp_db (integração real com banco)
"""
import base64
import datetime
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from candidatador.db import init_db, Job, Application


# ── helpers ───────────────────────────────────────────────────────────────────

BASE_EMAIL = "candidaturas@gmail.com"
BASE_STAGES = [
    "phone_screening", "technical_interview", "live_coding",
    "system_design", "culture_fit", "behavioral",
    "final_interview", "take_home_assignment", "reference_check",
]


def _make_llm_caller(response: dict):
    """Retorna um async caller que devolve `response` como JSON string."""
    async def caller(prompt, model=None):
        return json.dumps(response)
    return caller


def _gmail_service_mock(messages=None):
    """Monta um mock do resource do Gmail API."""
    service = MagicMock()
    msgs = messages or []
    list_response = {"messages": msgs} if msgs else {}
    (service.users().messages().list().execute
     .return_value) = list_response
    return service


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _build_gmail_message(to: str, from_: str, subject: str, body: str,
                         content_type: str = "text/plain") -> dict:
    """Monta estrutura de mensagem Gmail API."""
    return {
        "id": "msg123",
        "payload": {
            "headers": [
                {"name": "To", "value": to},
                {"name": "From", "value": from_},
                {"name": "Subject", "value": subject},
            ],
            "mimeType": content_type,
            "body": {"data": _b64(body)},
        }
    }


def _make_job(tmp_db, **kwargs):
    defaults = dict(
        source="greenhouse", company="Anthropic",
        title="Senior Engineer",
        url="https://boards.greenhouse.io/anthropic/jobs/1",
    )
    defaults.update(kwargs)
    return Job.create(**defaults)


def _make_application(job, **kwargs):
    defaults = dict(status="submitted")
    defaults.update(kwargs)
    return Application.create(job=job, **defaults)


# ── extract_ref ───────────────────────────────────────────────────────────────

class TestExtractRef:
    def test_alias_with_ref_returns_ref(self):
        from candidatador.email_monitor import extract_ref
        to = "candidaturas+x7k2mp@gmail.com"
        assert extract_ref(to, BASE_EMAIL) == "x7k2mp"

    def test_no_alias_returns_none(self):
        from candidatador.email_monitor import extract_ref
        assert extract_ref(BASE_EMAIL, BASE_EMAIL) is None

    def test_empty_string_returns_none(self):
        from candidatador.email_monitor import extract_ref
        assert extract_ref("", BASE_EMAIL) is None

    def test_unrelated_address_returns_none(self):
        from candidatador.email_monitor import extract_ref
        assert extract_ref("other@example.com", BASE_EMAIL) is None

    def test_strips_display_name(self):
        from candidatador.email_monitor import extract_ref
        to = "Alberto <candidaturas+abc123@gmail.com>"
        assert extract_ref(to, BASE_EMAIL) == "abc123"

    def test_multiple_recipients_finds_alias(self):
        from candidatador.email_monitor import extract_ref
        to = "hr@acme.com, candidaturas+zz9900@gmail.com"
        assert extract_ref(to, BASE_EMAIL) == "zz9900"

    def test_base_address_without_plus_returns_none(self):
        from candidatador.email_monitor import extract_ref
        to = "candidaturas@gmail.com"
        assert extract_ref(to, BASE_EMAIL) is None

    def test_different_domain_returns_none(self):
        from candidatador.email_monitor import extract_ref
        to = "candidaturas+ref123@hotmail.com"
        assert extract_ref(to, BASE_EMAIL) is None

    def test_ref_with_special_chars_in_urlsafe_b64(self):
        from candidatador.email_monitor import extract_ref
        to = "candidaturas+Ab-_12@gmail.com"
        assert extract_ref(to, BASE_EMAIL) == "Ab-_12"


# ── classify_response ─────────────────────────────────────────────────────────

class TestClassifyResponse:
    @pytest.fixture
    def message(self):
        return {
            "to": BASE_EMAIL,
            "from_": "recruiter@anthropic.com",
            "subject": "Próximos passos",
            "body": "Gostaríamos de agendar uma entrevista técnica.",
        }

    async def test_returns_interview_type(self, message):
        from candidatador.email_monitor import classify_response
        caller = _make_llm_caller({
            "type": "interview",
            "stage": "technical_interview",
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Entrevista técnica agendada.",
        })
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "interview"
        assert result["stage"] == "technical_interview"
        assert result["company"] == "Anthropic"

    async def test_returns_rejection(self, message):
        from candidatador.email_monitor import classify_response
        caller = _make_llm_caller({
            "type": "rejection",
            "stage": None,
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Infelizmente não avançaremos.",
        })
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "rejection"
        assert result["stage"] is None

    async def test_returns_offer(self, message):
        from candidatador.email_monitor import classify_response
        caller = _make_llm_caller({
            "type": "offer",
            "stage": None,
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Oferta formal enviada.",
        })
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "offer"

    async def test_returns_screening(self, message):
        from candidatador.email_monitor import classify_response
        caller = _make_llm_caller({
            "type": "screening",
            "stage": "phone_screening",
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Ligação inicial de 30min.",
        })
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "screening"
        assert result["stage"] == "phone_screening"

    async def test_returns_info_request(self, message):
        from candidatador.email_monitor import classify_response
        caller = _make_llm_caller({
            "type": "info_request",
            "stage": None,
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Precisamos de mais informações.",
        })
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "info_request"

    async def test_returns_unrelated(self, message):
        from candidatador.email_monitor import classify_response
        caller = _make_llm_caller({
            "type": "unrelated",
            "stage": None,
            "new_stage": None,
            "company": None,
            "job_title": None,
            "summary": "Newsletter de marketing.",
        })
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "unrelated"

    async def test_new_stage_populated_when_llm_proposes_unknown(self, message):
        from candidatador.email_monitor import classify_response
        caller = _make_llm_caller({
            "type": "interview",
            "stage": "pair_programming",
            "new_stage": "pair_programming",
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Sessão de pair programming.",
        })
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["new_stage"] == "pair_programming"

    async def test_json_fence_in_llm_response_handled(self, message):
        from candidatador.email_monitor import classify_response
        raw = {
            "type": "rejection",
            "stage": None,
            "new_stage": None,
            "company": "X",
            "job_title": "Eng",
            "summary": "Rejeitado.",
        }
        async def caller_with_fence(prompt, model=None):
            return f"```json\n{json.dumps(raw)}\n```"
        result = await classify_response(message, BASE_STAGES, caller_with_fence)
        assert result["type"] == "rejection"

    async def test_malformed_llm_response_returns_unrelated(self, message):
        from candidatador.email_monitor import classify_response
        async def bad_caller(prompt, model=None):
            return "não é JSON"
        result = await classify_response(message, BASE_STAGES, bad_caller)
        assert result["type"] == "unrelated"


# ── parse_message ─────────────────────────────────────────────────────────────

class TestParseMessage:
    def test_extracts_plain_text_body(self):
        from candidatador.email_monitor import parse_message
        raw_msg = _build_gmail_message(
            to=BASE_EMAIL,
            from_="hr@company.com",
            subject="Update",
            body="Parabéns, você avançou!",
            content_type="text/plain",
        )
        service = MagicMock()
        service.users().messages().get().execute.return_value = raw_msg

        result = parse_message(service, "msg123")

        assert result["to"] == BASE_EMAIL
        assert result["from_"] == "hr@company.com"
        assert result["subject"] == "Update"
        assert "Parabéns" in result["body"]

    def test_falls_back_to_html_when_no_plain(self):
        from candidatador.email_monitor import parse_message
        raw_msg = {
            "id": "msg456",
            "payload": {
                "headers": [
                    {"name": "To", "value": BASE_EMAIL},
                    {"name": "From", "value": "noreply@co.com"},
                    {"name": "Subject", "value": "HTML only"},
                ],
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": _b64("<p>Olá!</p>")},
                    }
                ],
            }
        }
        service = MagicMock()
        service.users().messages().get().execute.return_value = raw_msg

        result = parse_message(service, "msg456")
        assert "Olá" in result["body"]

    def test_prefers_plain_over_html_in_multipart(self):
        from candidatador.email_monitor import parse_message
        raw_msg = {
            "id": "msg789",
            "payload": {
                "headers": [
                    {"name": "To", "value": BASE_EMAIL},
                    {"name": "From", "value": "noreply@co.com"},
                    {"name": "Subject", "value": "Multipart"},
                ],
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": _b64("Texto puro")},
                    },
                    {
                        "mimeType": "text/html",
                        "body": {"data": _b64("<p>HTML</p>")},
                    },
                ],
            }
        }
        service = MagicMock()
        service.users().messages().get().execute.return_value = raw_msg

        result = parse_message(service, "msg789")
        assert result["body"] == "Texto puro"

    def test_handles_missing_body_gracefully(self):
        from candidatador.email_monitor import parse_message
        raw_msg = {
            "id": "msg000",
            "payload": {
                "headers": [
                    {"name": "To", "value": BASE_EMAIL},
                    {"name": "From", "value": "x@y.com"},
                    {"name": "Subject", "value": "Empty"},
                ],
                "mimeType": "text/plain",
                "body": {},
            }
        }
        service = MagicMock()
        service.users().messages().get().execute.return_value = raw_msg

        result = parse_message(service, "msg000")
        assert result["body"] == ""


# ── fetch_unread_messages ─────────────────────────────────────────────────────

class TestFetchUnreadMessages:
    def test_returns_list_of_id_and_thread_id(self):
        from candidatador.email_monitor import fetch_unread_messages
        service = MagicMock()
        msgs = [{"id": "a1", "threadId": "t1"}, {"id": "a2", "threadId": "t2"}]
        service.users().messages().list().execute.return_value = {"messages": msgs}

        result = fetch_unread_messages(service)

        assert len(result) == 2
        assert result[0]["id"] == "a1"
        assert result[1]["threadId"] == "t2"

    def test_returns_empty_list_when_no_messages(self):
        from candidatador.email_monitor import fetch_unread_messages
        service = MagicMock()
        service.users().messages().list().execute.return_value = {}

        result = fetch_unread_messages(service)
        assert result == []

    def test_respects_max_results(self):
        from candidatador.email_monitor import fetch_unread_messages
        service = MagicMock()
        service.users().messages().list().execute.return_value = {}

        fetch_unread_messages(service, max_results=10)

        call_kwargs = service.users().messages().list.call_args
        assert call_kwargs.kwargs.get("maxResults") == 10 or \
               10 in call_kwargs.args


# ── mark_processed ────────────────────────────────────────────────────────────

class TestMarkProcessed:
    def test_removes_unread_label_and_adds_processed_label(self):
        from candidatador.email_monitor import mark_processed
        service = MagicMock()
        service.users().messages().modify().execute.return_value = {}

        mark_processed(service, "msg123", "Label_123")

        modify_call = service.users().messages().modify.call_args
        body = modify_call.kwargs.get("body") or modify_call.args[0] if modify_call.args else {}
        if not body and modify_call.kwargs:
            body = modify_call.kwargs.get("body", {})

        assert "UNREAD" in body.get("removeLabelIds", [])
        assert "Label_123" in body.get("addLabelIds", [])

    def test_calls_execute(self):
        from candidatador.email_monitor import mark_processed
        service = MagicMock()
        service.users().messages().modify().execute.return_value = {}

        mark_processed(service, "msg123", "Label_xyz")

        assert service.users().messages().modify().execute.called


# ── setup_gmail_service ───────────────────────────────────────────────────────

class TestSetupGmailService:
    def test_returns_service_when_token_exists(self, tmp_path):
        from candidatador.email_monitor import setup_gmail_service, GmailAuthError

        token_path = str(tmp_path / "gmail-token.json")
        creds_path = str(tmp_path / "gmail-client.json")

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expired = False

        config = {
            "email": {
                "credentials_path": creds_path,
                "token_path": token_path,
            }
        }

        with patch("candidatador.email_monitor.Credentials") as MockCreds, \
             patch("candidatador.email_monitor.build") as mock_build, \
             patch("os.path.exists", return_value=True):
            MockCreds.from_authorized_user_file.return_value = mock_creds
            mock_build.return_value = MagicMock()

            service = setup_gmail_service(config)

        assert service is not None
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)

    def test_raises_gmail_auth_error_when_token_missing(self, tmp_path):
        from candidatador.email_monitor import setup_gmail_service, GmailAuthError

        config = {
            "email": {
                "credentials_path": str(tmp_path / "gmail-client.json"),
                "token_path": str(tmp_path / "nonexistent-token.json"),
            }
        }

        with pytest.raises(GmailAuthError, match="setup_email"):
            setup_gmail_service(config)

    def test_refreshes_expired_token(self, tmp_path):
        from candidatador.email_monitor import setup_gmail_service

        token_path = str(tmp_path / "gmail-token.json")
        config = {
            "email": {
                "credentials_path": str(tmp_path / "creds.json"),
                "token_path": token_path,
            }
        }

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "some-refresh-token"

        with patch("candidatador.email_monitor.Credentials") as MockCreds, \
             patch("candidatador.email_monitor.Request") as MockRequest, \
             patch("candidatador.email_monitor.build") as mock_build, \
             patch("os.path.exists", return_value=True), \
             patch("builtins.open", MagicMock()):
            MockCreds.from_authorized_user_file.return_value = mock_creds
            mock_build.return_value = MagicMock()

            setup_gmail_service(config)

        mock_creds.refresh.assert_called_once()


# ── sync_responses (integração real com banco) ────────────────────────────────

class TestSyncResponses:
    """
    Usa tmp_db pra DB real + mock do Gmail service.
    Cada test cria vagas/candidaturas necessárias.
    """

    CONFIG = {
        "email": {
            "address": BASE_EMAIL,
            "credentials_path": "~/.candidatador/gmail-client.json",
            "token_path": "~/.candidatador/gmail-token.json",
            "processed_label": "candidatador/processado",
            "interview_stages": list(BASE_STAGES),
        },
        "llm_model": "claude-sonnet-4-6",
    }

    def _mock_service(self, messages_raw: list[dict]):
        """Monta serviço com lista de mensagens já parseadas (dict com to/from_/subject/body)."""
        service = MagicMock()
        service.users().messages().list().execute.return_value = {
            "messages": [{"id": f"msg{i}", "threadId": f"t{i}"}
                         for i in range(len(messages_raw))]
        }
        service.users().messages().modify().execute.return_value = {}
        return service

    async def test_email_with_ref_updates_application_status(self, tmp_db):
        init_db()
        job = _make_job(tmp_db)
        app = _make_application(job, status="submitted", email_ref="x7k2mp")

        messages = [
            {
                "to": "candidaturas+x7k2mp@gmail.com",
                "from_": "hr@anthropic.com",
                "subject": "Entrevista técnica",
                "body": "Olá, gostaríamos de agendar entrevista.",
            }
        ]
        classify_result = {
            "type": "interview",
            "stage": "technical_interview",
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Entrevista técnica agendada.",
        }

        service = self._mock_service(messages)

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=service), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message",
                   return_value=messages[0]), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed") as mock_mark, \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            updates = await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        app_refreshed = Application.get_by_id(app.id)
        assert app_refreshed.status == "interviews"
        assert app_refreshed.current_stage == "technical_interview"
        assert "[" in app_refreshed.notes  # tem data
        assert "match: ref" in app_refreshed.notes
        mock_mark.assert_called_once()
        assert len(updates) == 1

    async def test_email_without_ref_fuzzy_match_by_company_and_title(self, tmp_db):
        init_db()
        job = _make_job(tmp_db, company="Stripe", title="Backend Engineer")
        app = _make_application(job, status="submitted", email_ref=None)

        message = {
            "to": BASE_EMAIL,
            "from_": "talent@stripe.com",
            "subject": "Next steps",
            "body": "Hi, moving forward with your application for Backend Engineer.",
        }
        classify_result = {
            "type": "interview",
            "stage": "technical_interview",
            "new_stage": None,
            "company": "Stripe",
            "job_title": "Backend Engineer",
            "summary": "Entrevista técnica.",
        }

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed"), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        app_refreshed = Application.get_by_id(app.id)
        assert app_refreshed.status == "interviews"
        assert "match: fuzzy" in app_refreshed.notes

    async def test_ambiguous_match_marks_incerto_in_notes(self, tmp_db):
        init_db()
        job1 = _make_job(tmp_db, company="Stripe", title="Engineer",
                         url="https://x.com/1")
        job2 = _make_job(tmp_db, company="Stripe", title="Engineer",
                         url="https://x.com/2")
        app1 = _make_application(job1, status="submitted", email_ref=None)
        app2 = _make_application(job2, status="submitted", email_ref=None)

        message = {
            "to": BASE_EMAIL,
            "from_": "hr@stripe.com",
            "subject": "Update",
            "body": "Seguindo com sua candidatura para Engineer.",
        }
        classify_result = {
            "type": "interview",
            "stage": "phone_screening",
            "new_stage": None,
            "company": "Stripe",
            "job_title": "Engineer",
            "summary": "Ligação inicial.",
        }

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed"), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            updates = await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        # Nenhuma application pode ter sido atualizada definitivamente — incerto
        assert any("incerto" in (u.get("match_type", "")) for u in updates)

    async def test_rejection_sets_status_rejected(self, tmp_db):
        init_db()
        job = _make_job(tmp_db)
        app = _make_application(job, status="submitted", email_ref="rej001")

        classify_result = {
            "type": "rejection",
            "stage": None,
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Não avançaremos com sua candidatura.",
        }
        message = {
            "to": "candidaturas+rej001@gmail.com",
            "from_": "noreply@anthropic.com",
            "subject": "Sua candidatura",
            "body": "Obrigado pelo interesse.",
        }

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed"), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        assert Application.get_by_id(app.id).status == "rejected"

    async def test_status_never_regresses(self, tmp_db):
        """Email de screening não pode regredir uma candidatura já em 'interviews'."""
        init_db()
        job = _make_job(tmp_db)
        app = _make_application(job, status="interviews", email_ref="nrg001",
                                 current_stage="technical_interview")

        classify_result = {
            "type": "screening",
            "stage": "phone_screening",
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Agendamos uma ligação inicial.",
        }
        message = {
            "to": "candidaturas+nrg001@gmail.com",
            "from_": "hr@anthropic.com",
            "subject": "Ligação",
            "body": "Vamos marcar uma ligação.",
        }

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed"), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        app_refreshed = Application.get_by_id(app.id)
        assert app_refreshed.status == "interviews"  # não regrediu

    async def test_info_request_keeps_current_status(self, tmp_db):
        init_db()
        job = _make_job(tmp_db)
        app = _make_application(job, status="screening", email_ref="inf001")

        classify_result = {
            "type": "info_request",
            "stage": None,
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Precisamos de mais informações.",
        }
        message = {
            "to": "candidaturas+inf001@gmail.com",
            "from_": "hr@anthropic.com",
            "subject": "Informações",
            "body": "Pode nos enviar seu portfólio?",
        }

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed"), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        assert Application.get_by_id(app.id).status == "screening"

    async def test_unrelated_email_skipped_and_marked_processed(self, tmp_db):
        init_db()
        job = _make_job(tmp_db)
        app = _make_application(job, status="submitted", email_ref="unr001")

        classify_result = {
            "type": "unrelated",
            "stage": None,
            "new_stage": None,
            "company": None,
            "job_title": None,
            "summary": "Newsletter de marketing.",
        }
        message = {
            "to": "candidaturas+unr001@gmail.com",
            "from_": "news@company.com",
            "subject": "Promoção!",
            "body": "Confira nossas ofertas.",
        }

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed") as mock_mark, \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            updates = await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        # Application não foi tocada
        assert Application.get_by_id(app.id).status == "submitted"
        # Mas mark_processed foi chamado
        mock_mark.assert_called_once()
        # Não retorna update pro unrelated
        assert len(updates) == 0

    async def test_new_stage_added_to_config(self, tmp_db):
        init_db()
        job = _make_job(tmp_db)
        _make_application(job, status="submitted", email_ref="new001")

        classify_result = {
            "type": "interview",
            "stage": "pair_programming",
            "new_stage": "pair_programming",
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Sessão de pair programming.",
        }
        message = {
            "to": "candidaturas+new001@gmail.com",
            "from_": "hr@anthropic.com",
            "subject": "Pair session",
            "body": "Vamos fazer pair programming.",
        }

        config = {**self.CONFIG, "email": {**self.CONFIG["email"],
                                            "interview_stages": list(BASE_STAGES)}}

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed"), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            await sync_responses(config, _make_llm_caller(classify_result))

        assert "pair_programming" in config["email"]["interview_stages"]

    async def test_notes_include_date_and_match_type(self, tmp_db):
        init_db()
        job = _make_job(tmp_db)
        app = _make_application(job, status="submitted", email_ref="nt001",
                                 notes=None)

        classify_result = {
            "type": "interview",
            "stage": "technical_interview",
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Entrevista técnica agendada para 05/06.",
        }
        message = {
            "to": "candidaturas+nt001@gmail.com",
            "from_": "hr@anthropic.com",
            "subject": "Entrevista",
            "body": "Gostaríamos de agendar.",
        }

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed"), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        notes = Application.get_by_id(app.id).notes
        today = datetime.date.today().strftime("%Y-%m-%d")
        assert today in notes
        assert "interview" in notes
        assert "Entrevista técnica agendada" in notes
        assert "match: ref" in notes

    async def test_notes_appended_to_existing_notes(self, tmp_db):
        init_db()
        job = _make_job(tmp_db)
        existing_notes = "[2026-05-01] screening: Ligação inicial. (match: fuzzy)"
        app = _make_application(job, status="screening", email_ref="app001",
                                 notes=existing_notes)

        classify_result = {
            "type": "interview",
            "stage": "technical_interview",
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Entrevista técnica.",
        }
        message = {
            "to": "candidaturas+app001@gmail.com",
            "from_": "hr@anthropic.com",
            "subject": "Entrevista técnica",
            "body": "Próximo passo.",
        }

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed"), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        notes = Application.get_by_id(app.id).notes
        assert existing_notes in notes
        assert "technical_interview" in notes or "interview" in notes

    async def test_updated_at_refreshed_after_email_sync(self, tmp_db):
        init_db()
        job = _make_job(tmp_db)
        old_time = datetime.datetime(2026, 1, 1)
        app = _make_application(job, status="submitted", email_ref="upd001",
                                 updated_at=old_time)

        classify_result = {
            "type": "rejection",
            "stage": None,
            "new_stage": None,
            "company": "Anthropic",
            "job_title": "Senior Engineer",
            "summary": "Rejeitado.",
        }
        message = {
            "to": "candidaturas+upd001@gmail.com",
            "from_": "hr@anthropic.com",
            "subject": "Update",
            "body": ".",
        }

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[{"id": "msg0", "threadId": "t0"}]), \
             patch("candidatador.email_monitor.parse_message", return_value=message), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed"), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        app_refreshed = Application.get_by_id(app.id)
        assert app_refreshed.updated_at > old_time

    async def test_mark_processed_called_for_every_email(self, tmp_db):
        init_db()
        classify_result = {
            "type": "unrelated",
            "stage": None,
            "new_stage": None,
            "company": None,
            "job_title": None,
            "summary": "Spam.",
        }
        messages = [
            {"to": BASE_EMAIL, "from_": "a@a.com", "subject": "A", "body": "a"},
            {"to": BASE_EMAIL, "from_": "b@b.com", "subject": "B", "body": "b"},
            {"to": BASE_EMAIL, "from_": "c@c.com", "subject": "C", "body": "c"},
        ]
        raw_ids = [{"id": f"msg{i}", "threadId": f"t{i}"} for i in range(3)]

        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=raw_ids), \
             patch("candidatador.email_monitor.parse_message",
                   side_effect=messages), \
             patch("candidatador.email_monitor.classify_response",
                   new=AsyncMock(return_value=classify_result)), \
             patch("candidatador.email_monitor.mark_processed") as mock_mark, \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            await sync_responses(self.CONFIG, _make_llm_caller(classify_result))

        assert mock_mark.call_count == 3

    async def test_returns_empty_list_when_no_emails(self, tmp_db):
        init_db()
        with patch("candidatador.email_monitor.setup_gmail_service", return_value=MagicMock()), \
             patch("candidatador.email_monitor.fetch_unread_messages",
                   return_value=[]), \
             patch("candidatador.email_monitor._get_or_create_label",
                   return_value="Label_proc"):
            from candidatador.email_monitor import sync_responses
            updates = await sync_responses(self.CONFIG, _make_llm_caller({}))

        assert updates == []
