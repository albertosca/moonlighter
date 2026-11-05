"""The config and Gmail service mock the sync_responses tests run against.

Those tests use temporary_database for a real DB and create the jobs and applications
they need; only Gmail is mocked.
"""

from unittest.mock import MagicMock

from tests.tracking.tracking_settings import BASE_EMAIL, BASE_STAGES

SYNC_CONFIG: dict = {
    "email": {
        "address": BASE_EMAIL,
        "credentials_path": "~/.moonlighter/gmail-client.json",
        "token_path": "~/.moonlighter/gmail-token.json",
        "processed_label": "moonlighter/processed",
        "interview_stages": list(BASE_STAGES),
    },
    "llm_model": "claude-sonnet-4-6",
}


def mock_service(messages_raw: list[dict]):
    """Builds a service with a list of already-parsed messages (dict with to/from_/subject/body)."""
    service = MagicMock()
    service.users().messages().list().execute.return_value = {
        "messages": [
            {"id": f"msg{index}", "threadId": f"t{index}"} for index in range(len(messages_raw))
        ]
    }
    service.users().messages().modify().execute.return_value = {}
    return service
