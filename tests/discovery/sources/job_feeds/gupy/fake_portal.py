"""A Gupy search page and the fake client that serves it, shared by the Gupy tests."""

GUPY_P1 = {
    "data": [
        {
            "id": 1,
            "name": "Engenheiro de Software",
            "jobUrl": "https://acme.gupy.io/job/tok?jobBoardSource=gupy_portal",
            "careerPageName": "acme",
            "description": "Construir&nbsp;coisas",
            "city": "",
            "state": "",
            "country": "Brasil",
            "isRemoteWork": True,
            "workplaceType": "remote",
        }
    ],
    "pagination": {"total": 1, "limit": 10, "offset": 0},
}
