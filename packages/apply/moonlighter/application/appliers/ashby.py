from typing import ClassVar

from moonlighter.application.appliers.simple_form import SimpleFormApplier


class AshbyApplier(SimpleFormApplier):
    URL_HOSTS = ("ashbyhq.com", "jobs.ashbyhq.com")
    FORM_SELECTOR = "form"
    LABEL_SELECTORS: ClassVar[list[str]] = [
        "label",
        ".ashby-application-form label",
        "[class*='label']:not(legend)",
    ]
    SUBMIT_SELECTOR = "button[type='submit']"
