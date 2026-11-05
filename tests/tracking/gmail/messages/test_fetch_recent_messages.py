"""Fetching recent messages: the search, its cap warnings and pagination."""

import logging
from unittest.mock import MagicMock

from moonlighter.tracking.gmail.messages import _MAXIMUM_PAGES, fetch_recent_messages


class TestFetchRecentMessages:
    def test_searches_spam_as_well_as_the_inbox(self):
        """ATS confirmations sent to a plus-alias land in spam regularly — one did,
        for the holepunch application on 2026-08-04, and the monitor could not see
        it: SPAM is a separate label from INBOX, so labelIds=[INBOX] hid it entirely.
        "We received your application" is the reply least worth missing.
        """
        service = MagicMock()
        listing = service.users.return_value.messages.return_value.list
        listing.return_value.execute.return_value = {"messages": []}

        fetch_recent_messages(service)

        call_keyword_arguments = listing.call_args.kwargs
        assert "in:anywhere" in call_keyword_arguments.get("q", "")
        assert "labelIds" not in call_keyword_arguments, "labelIds=[INBOX] would exclude spam"

    def test_does_not_gate_on_read_state(self):
        """A person reads their mail; a reply already read is exactly the reply
        worth recording. Re-processing is prevented by ProcessedEmail, not by
        the unread flag.
        """
        service = MagicMock()
        listing = service.users.return_value.messages.return_value.list
        listing.return_value.execute.return_value = {"messages": []}

        fetch_recent_messages(service)

        call_keyword_arguments = listing.call_args.kwargs
        assert "is:unread" not in call_keyword_arguments.get("q", "")

    def test_bounds_the_search_by_the_lookback_window(self):
        service = MagicMock()
        listing = service.users.return_value.messages.return_value.list
        listing.return_value.execute.return_value = {"messages": []}

        fetch_recent_messages(service, lookback_days=7)

        call_keyword_arguments = listing.call_args.kwargs
        assert "newer_than:7d" in call_keyword_arguments.get("q", "")

    def test_returns_list_of_id_and_thread_id(self):
        service = MagicMock()
        resolved_messages = [{"id": "a1", "threadId": "t1"}, {"id": "a2", "threadId": "t2"}]
        service.users().messages().list().execute.return_value = {"messages": resolved_messages}

        result = fetch_recent_messages(service)

        assert len(result) == 2
        assert result[0]["id"] == "a1"
        assert result[1]["threadId"] == "t2"

    def test_returns_empty_list_when_no_messages(self):
        service = MagicMock()
        service.users().messages().list().execute.return_value = {}

        result = fetch_recent_messages(service)
        assert result == []

    def test_respects_max_results(self):
        service = MagicMock()
        service.users().messages().list().execute.return_value = {}

        fetch_recent_messages(service, maximum_results=10)

        list_call_arguments = service.users().messages().list.call_args
        assert list_call_arguments.kwargs.get("maxResults") == 10 or 10 in list_call_arguments.args

    def test_warns_when_a_page_hits_the_cap(self, caplog):
        """Whole-branch Finding 2: silent truncation at the 50-message cap must
        never be silent — a full page has to log a clear warning, since a
        mailbox with more than maximum_results messages inside the lookback window
        would otherwise lose the older ones with no signal at all (unlike the
        old is:unread design, this time-window design has no drain).
        """
        service = MagicMock()
        full_page = {
            "messages": [{"id": f"m{index}", "threadId": f"t{index}"} for index in range(3)]
        }
        service.users().messages().list().execute.return_value = full_page

        with caplog.at_level(logging.WARNING, logger="moonlighter.tracking.gmail.messages"):
            result = fetch_recent_messages(service, maximum_results=3)

        assert len(result) == 3
        assert "3" in caplog.text  # names the cap that was hit

    def test_does_not_warn_when_below_the_cap(self, caplog):
        service = MagicMock()
        service.users().messages().list().execute.return_value = {
            "messages": [{"id": "m0", "threadId": "t0"}]
        }

        with caplog.at_level(logging.WARNING, logger="moonlighter.tracking.gmail.messages"):
            fetch_recent_messages(service, maximum_results=50)

        assert caplog.text == ""

    def test_paginates_via_next_page_token_across_multiple_pages(self):
        """A mailbox with more messages than maximum_results must not silently
        truncate — fetch_recent_messages follows nextPageToken to collect them
        all, up to the hard page bound.
        """
        service = MagicMock()
        responses = [
            {
                "messages": [{"id": "m0", "threadId": "t0"}, {"id": "m1", "threadId": "t1"}],
                "nextPageToken": "page2",
            },
            {"messages": [{"id": "m2", "threadId": "t2"}]},
        ]
        service.users().messages().list().execute.side_effect = responses

        result = fetch_recent_messages(service, maximum_results=2)

        assert [message["id"] for message in result] == ["m0", "m1", "m2"]

    def test_second_page_request_carries_the_returned_page_token(self):
        service = MagicMock()
        listing = service.users.return_value.messages.return_value.list
        listing.return_value.execute.side_effect = [
            {"messages": [{"id": "m0", "threadId": "t0"}], "nextPageToken": "page2"},
            {"messages": [{"id": "m1", "threadId": "t1"}]},
        ]

        fetch_recent_messages(service, maximum_results=1)

        second_call_keyword_arguments = listing.call_args_list[1].kwargs
        assert second_call_keyword_arguments.get("pageToken") == "page2"

    def test_stops_at_the_hard_page_bound_and_warns(self, caplog):
        """Even if Gmail keeps returning nextPageToken forever, pagination must
        stop at a bounded number of pages so a huge mailbox can't spin forever —
        and hitting that bound is logged, same as hitting maximum_results.
        """
        service = MagicMock()
        # Every page is below maximum_results (so the per-page warning doesn't fire)
        # but always carries a nextPageToken, forcing the hard page-count bound.
        service.users().messages().list().execute.return_value = {
            "messages": [{"id": "m", "threadId": "t"}],
            "nextPageToken": "more",
        }

        with caplog.at_level(logging.WARNING, logger="moonlighter.tracking.gmail.messages"):
            result = fetch_recent_messages(service, maximum_results=50)

        assert len(result) == _MAXIMUM_PAGES
        assert "page" in caplog.text.lower()
