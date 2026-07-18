from gauntler.application.answers.email_alias import build_email_alias, inject_email_alias


def test_build_email_alias_formats_correctly():
    result = build_email_alias("candidaturas@gmail.com", "x7k2mp")
    assert result == "candidaturas+x7k2mp@gmail.com"


def test_build_email_alias_different_refs():
    assert build_email_alias("a@b.com", "abc") == "a+abc@b.com"
    assert build_email_alias("a@b.com", "xyz") == "a+xyz@b.com"


def test_inject_email_alias_matches_ptbr_e_mail_label():
    """Label 'E-mail' (PT, with a hyphen) must receive the alias — without the hyphen
    breaking the match or creating a phantom 'Email' field."""
    answers = {"E-mail*": "pessoal@gmail.com", "Nome*": "Alberto"}
    injected = inject_email_alias(answers, "candidaturas+abc123@gmail.com")
    assert injected is True
    assert answers["E-mail*"] == "candidaturas+abc123@gmail.com"
    assert "Email" not in answers  # doesn't create a phantom field


def test_inject_email_alias_matches_plain_email_label():
    answers = {"Email": "pessoal@gmail.com"}
    inject_email_alias(answers, "x+ref@y.com")
    assert answers["Email"] == "x+ref@y.com"


def test_inject_email_alias_fallback_when_no_email_field():
    answers = {"Nome*": "Alberto"}
    injected = inject_email_alias(answers, "x+ref@y.com")
    assert injected is False
    assert answers["Email"] == "x+ref@y.com"  # fallback
