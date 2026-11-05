"""The recorded Recruitee offers the tests read their questions from."""

import json

from tests.application.assisted.sources.fixture_files import FIXTURES_DIRECTORY

PAYLOAD = json.loads((FIXTURES_DIRECTORY / "recruitee_offer.json").read_text())
PAYLOAD_WITH_CHOICE = json.loads(
    (FIXTURES_DIRECTORY / "recruitee_offer_with_choice.json").read_text()
)
PAYLOAD_WITH_BOOLEAN_AND_DATE = json.loads(
    (FIXTURES_DIRECTORY / "recruitee_offer_with_boolean_and_date.json").read_text()
)
