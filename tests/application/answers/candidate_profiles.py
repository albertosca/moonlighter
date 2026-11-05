"""Candidate profiles that more than one answers test module reads."""

PROFILE = {
    "name": "Maria de Souza Pereira",
    "phone": "11912345678",
    "email": "maria.pereira@example.com",
    "linkedin": "https://www.linkedin.com/in/mariapereira/",
    "github": "https://github.com/mariapereira",
    "location": "São Paulo, SP, Brasil",
    # generic location/language/availability fields
    "country_en": "Brazil",
    "country_pt": "Brasil",
    "english_level": "Fluent",
    "office_available": True,
    # EEO/demographic self-identification — English-only, nested under "demographics"
    # (same shape Alberto already configured in his real profile.yaml on 2026-08-04).
    "demographics": {
        "gender": "Male",
        "hispanic_latino": "Yes",
        "race": "White",
        "veteran_status": "No",
        "disability_status": "No",
    },
}
