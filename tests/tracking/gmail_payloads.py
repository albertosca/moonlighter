"""Gmail payload encoding for the tracking tests."""

import base64


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()
