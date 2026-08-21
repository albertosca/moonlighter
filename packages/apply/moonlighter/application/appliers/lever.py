from typing import ClassVar

from moonlighter.application.appliers.simple_form import SimpleFormApplier


class LeverApplier(SimpleFormApplier):
    URL_HOSTS = ("jobs.lever.co",)
    FORM_SELECTOR = ".application-form"
    LABEL_SELECTORS: ClassVar[list[str]] = [
        ".application-label, label",
        ".lever-application-form label",
        "[class*='label']",
    ]
    SUBMIT_SELECTOR = "button[type='submit'], .template-btn-submit"
