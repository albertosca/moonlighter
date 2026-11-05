"""PT-BR labels: the Portuguese spellings of the contact and location rules."""

from moonlighter.application.answers.matching.field_map import pre_populate_answers
from tests.application.answers.candidate_profiles import PROFILE


def test_ptbr_nome_first_name():
    result = pre_populate_answers(["Nome"], PROFILE)
    assert result["Nome"] == "Maria"


def test_ptbr_sobrenome_last_name():
    result = pre_populate_answers(["Sobrenome"], PROFILE)
    assert result["Sobrenome"] == "de Souza Pereira"


def test_ptbr_nome_de_preferencia():
    result = pre_populate_answers(["Nome de preferência"], PROFILE)
    assert result["Nome de preferência"] == "Maria"


def test_ptbr_email():
    result = pre_populate_answers(["E-mail"], PROFILE)
    assert result["E-mail"] == "maria.pereira@example.com"


def test_ptbr_telefone():
    result = pre_populate_answers(["Telefone"], PROFILE)
    assert result["Telefone"] == "11912345678"


def test_ptbr_pais_brasil():
    result = pre_populate_answers(["País"], PROFILE)
    assert result["País"] == "Brasil"


def test_ptbr_localizacao_cidade():
    result = pre_populate_answers(["Localização (Cidade)"], PROFILE)
    assert result["Localização (Cidade)"] == "São Paulo"


def test_currently_based_question_fills_city():
    """'Where are you currently based?' keeps pre-populating the city."""
    result = pre_populate_answers(["Where are you currently based?"], PROFILE)
    assert result["Where are you currently based?"] == "São Paulo"


def test_currently_based_midsentence_confirmation_not_prepopulated():
    """A confirmation field that CONTAINS 'currently based' mid-sentence is NOT treated
    as the city (leaves it for the LLM to answer 'Yes, I am aware').
    """
    label = (
        "You are aware that this is a hybrid position and we require you to be "
        'currently based in one of the job post locations. Type "Yes, I am aware" if you confirm.'
    )
    result = pre_populate_answers([label], PROFILE)
    assert label not in result
