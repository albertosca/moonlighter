"""The archive-flag config the archive tests sync with: one stage, relative token paths."""

from tests.tracking.tracking_settings import BASE_EMAIL

ARCHIVE_STAGES = ["technical_interview"]  # one stage, unlike the shared nine in tracking_settings


def archive_config(**email_flags):
    return {
        "email": {
            "address": BASE_EMAIL,
            "credentials_path": "gmail-client.json",
            "token_path": "gmail-token.json",
            "interview_stages": list(ARCHIVE_STAGES),
            **email_flags,
        },
        "llm_model": "claude-sonnet-4-6",
    }
