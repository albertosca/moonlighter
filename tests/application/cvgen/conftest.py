import pytest

from tests.application.cvgen.sample_tailored_cv import POOL_YAML, TEMPLATE


@pytest.fixture
def config(tmp_path):
    pool = tmp_path / "cv-pool.yaml"
    pool.write_text(POOL_YAML)
    template_directory = tmp_path / "templates"
    template_directory.mkdir()
    (template_directory / "cv-template.en.tex").write_text(TEMPLATE)
    return {
        "cv": {
            "pool": str(pool),
            "template_dir": str(template_directory),
            "generated_dir": str(tmp_path / "generated"),
        }
    }
