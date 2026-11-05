"""The recent-messages search: read state must not gate what the tracker sees."""

from typing import Any

from moonlighter.tracking.gmail_messages import fetch_recent_messages


class FakeMessages:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def list(self, userId: str, pageToken: str | None = None, **search_parameters: Any) -> Any:  # noqa: N803 - mirrors the Gmail API's keyword names
        """Records the search query of a Gmail ``messages().list`` call.

        The Gmail client library takes ``q`` and ``maxResults`` as keywords, and the
        project's naming policy forbids both as identifiers, so they arrive by key and
        are checked here: a call that drops or renames one fails instead of passing.
        """
        expected = {"q", "maxResults"}
        if set(search_parameters) != expected:
            missing = sorted(expected - set(search_parameters))
            unexpected = sorted(set(search_parameters) - expected)
            raise TypeError(
                f"messages().list() keywords: missing {missing}, unexpected {unexpected}"
            )
        self.queries.append(search_parameters["q"])
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
        self.messages = FakeMessages()

    def users(self) -> FakeUsers:
        return FakeUsers(self.messages)


def test_read_state_is_not_part_of_the_search():
    # A person reads their mail; a tracker that only sees unread sees nothing.
    service = FakeService()
    fetch_recent_messages(service)
    assert "is:unread" not in service.messages.queries[0]


def test_the_search_is_bounded_by_the_lookback_window():
    service = FakeService()
    fetch_recent_messages(service, lookback_days=7)
    assert "newer_than:7d" in service.messages.queries[0]


def test_the_search_covers_archived_and_spam():
    service = FakeService()
    fetch_recent_messages(service)
    assert "in:anywhere" in service.messages.queries[0]


def test_the_messages_come_back():
    assert fetch_recent_messages(FakeService()) == [{"id": "abc"}]
