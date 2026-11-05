"""Matching a reply to its application by the reference in its plus-alias."""

import pytest
from moonlighter.tracking.application_matching import _match_by_ref


@pytest.mark.parametrize("looked_up", ["nt7eig", "NT7EIG", "Nt7eig"])
def test_a_stored_mixed_case_ref_matches_whatever_case_the_reply_carries(
    application_factory, looked_up
):
    # The refs already in the database were minted in mixed case; a reply arriving
    # lowercased must still find them, or the alias mechanism is decorative.
    application = application_factory(email_ref="Nt7eig")
    assert _match_by_ref(looked_up).id == application.id


def test_an_unknown_ref_still_matches_nothing(application_factory):
    application_factory(email_ref="Nt7eig")
    assert _match_by_ref("zzzzzz") is None
