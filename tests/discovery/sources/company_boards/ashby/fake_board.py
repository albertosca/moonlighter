"""An Ashby posting and the board response that wraps it, shared by the Ashby tests."""


# The GraphQL board API these tests used to target was retired: it answers HTTP 200
# with {"errors":[{"message":'Cannot query field "jobPostings" on type "Query"'}]},
# which the scanner turned into [] — so every Ashby company reported zero openings
# and nothing was logged. Field shapes below are copied from a live response of the
# current endpoint (api.ashbyhq.com/posting-api/job-board/<slug>), 2026-08-03.


def ashby_response(*jobs):
    return {"jobs": list(jobs), "apiVersion": "v1"}


ASHBY_JOB = {
    "id": "d3bc1ced",
    "title": "ML Engineer",
    "location": "Remote",
    "isRemote": True,
    "isListed": True,
    "publishedAt": "2026-05-01T20:13:45.158+00:00",
    "descriptionPlain": "Train and serve large language models.",
    "jobUrl": "https://jobs.ashbyhq.com/openai/d3bc1ced",
}
