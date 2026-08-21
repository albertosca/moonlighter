from enum import StrEnum


class Source(StrEnum):
    """The set of job sources / ATS platforms the system knows about.

    A StrEnum: each member IS its lowercase string value, so members compare and
    hash equal to the plain strings stored in Job.source and used as dict keys —
    no conversion needed at call sites.
    """

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    LINKEDIN = "linkedin"
    WORKABLE = "workable"
    SMARTRECRUITERS = "smartrecruiters"
    RECRUITEE = "recruitee"
    INHIRE = "inhire"
    GUPY = "gupy"
    REMOTEOK = "remoteok"
    REMOTIVE = "remotive"
    WEWORKREMOTELY = "weworkremotely"
    HN_WHOISHIRING = "hn_whoishiring"
