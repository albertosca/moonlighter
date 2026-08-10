"""
Tests for the recent-messages search: read state must not gate what the tracker sees.
"""

from typing import Any

from moonlighter.tracking.gmail_client import fetch_recent_messages


class FakeMessages:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def list(self, userId: str, q: str, maxResults: int) -> Any:
        self.queries.append(q)
        return self

    def execute(self) -> dict[str, Any]:
        return {"messages": [{"id": "abc"}]}


class FakeUsers:
    def __init__(self, messages: FakeMessages) -> None:
        self._messages = messages

    def messages(self) -> FakeMessages:
        return self._messages


class FakeService:
    def __init__(self) -> None:
        self.msgs = FakeMessages()

    def users(self) -> FakeUsers:
        return FakeUsers(self.msgs)


def test_read_state_is_not_part_of_the_search():
    # A person reads their mail; a tracker that only sees unread sees nothing.
    service = FakeService()
    fetch_recent_messages(service)
    assert "is:unread" not in service.msgs.queries[0]


def test_the_search_is_bounded_by_the_lookback_window():
    service = FakeService()
    fetch_recent_messages(service, lookback_days=7)
    assert "newer_than:7d" in service.msgs.queries[0]


def test_the_search_covers_archived_and_spam():
    service = FakeService()
    fetch_recent_messages(service)
    assert "in:anywhere" in service.msgs.queries[0]


def test_the_messages_come_back():
    assert fetch_recent_messages(FakeService()) == [{"id": "abc"}]
