"""The static rule ladder's order: which profile value answers which label, first match winning."""

from moonlighter.application.answers.static_rules import _RULES

EXPECTED_PATTERN_ORDER = [
    r"^(your\s+)?full\s+name",
    r"^(your\s+)?name$",
    r"^first\s+name",
    r"^last\s+name",
    r"preferred\s+(first\s+)?name",
    r"^(phone|telephone|mobile|cel)",
    r"^e-?mail",
    r"linkedin",
    r"github",
    r"^(website|portfolio|personal\s+site)",
    (
        r"^(?:(?:what\s+is|what[’']s|what\s+are)\s+your\s+|qual\s+(?:é\s+)?(?:a\s+)?sua\s+)?"
        r"(?:(?:desired|expected|current|target|minimum|base|total)\s+)?"
        r"(?:salary|compensation|pay|pretens\w*|remunera\w*|sal[aá]rio|faixa\s+salarial)"
        r"(?:\s+(?:expectations?|requirements?|range|salari\w*|pretendid\w*|desejad\w*"
        r"|mensa(?:l|is)|monthly|anual|annual|target|desired|expected))*"
        r"\s*\??\s*(?:\([^)]{0,15}\))?\s*\??\s*:?\s*$"
    ),
    r"nome\s+de\s+prefer|prefer.*nome",
    r"^sobrenome",
    r"^nome\s+completo",
    r"^nome",
    r"^(telefone|celular)",
    r"location\s*\(?city",
    r"localiza|^cidade",
    r"^city$",
    r"^country$",
    r"^pa[ií]s",
    r"^address$",
    r"english\s+level|english\s+proficiency|profici.*english",
    r"work\s+from\s+the\s+office|office\s+at\s+least",
    r"^where\s+are\s+you\s+(currently\s+)?based|^current\s+location|^currently\s+based",
]


def test_the_rules_keep_their_order_because_the_first_match_wins():
    assert [pattern for pattern, _rule in _RULES] == EXPECTED_PATTERN_ORDER
