from moonlighter.core.sources import Source


def test_members_serialize_to_plain_strings():
    assert Source.GREENHOUSE == "greenhouse"
    assert Source.LEVER == "lever"
    assert Source.ASHBY == "ashby"
    assert Source.LINKEDIN == "linkedin"


def test_str_and_fstring_yield_plain_value():
    assert str(Source.GREENHOUSE) == "greenhouse"
    assert f"{Source.ASHBY}" == "ashby"


def test_is_iterable_over_all_sources():
    assert {s.value for s in Source} == {
        "greenhouse",
        "lever",
        "ashby",
        "linkedin",
        "workable",
        "smartrecruiters",
        "recruitee",
        "gupy",
        "remoteok",
        "remotive",
        "weworkremotely",
        "hn_whoishiring",
    }


def test_str_key_lookup_matches_member_key():
    # StrEnum members hash-equal their str value, so dict lookups interop.
    d = {Source.GREENHOUSE: 1}
    assert d["greenhouse"] == 1


def test_source_has_remote_board_members():
    from moonlighter.core.sources import Source

    assert Source.REMOTEOK == "remoteok"
    assert Source.REMOTIVE == "remotive"
    assert Source.WEWORKREMOTELY == "weworkremotely"
    assert Source.HN_WHOISHIRING == "hn_whoishiring"
