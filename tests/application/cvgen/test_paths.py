from moonlighter.application.cvgen.paths import resolved_pool_path, resolved_template_dir
from moonlighter.core.config.loading import build_config


def test_resolved_pool_path_falls_back_to_a_default_under_moonlighter_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert resolved_pool_path(build_config({})) == tmp_path / "cv-pool.yaml"


def test_resolved_pool_path_honors_an_explicit_config_value(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert (
        resolved_pool_path(build_config({"cv": {"pool": "my-pool.yaml"}}))
        == tmp_path / "my-pool.yaml"
    )


def test_resolved_template_dir_falls_back_to_a_default_under_moonlighter_home(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert resolved_template_dir(build_config({})) == tmp_path / "cv-templates"


def test_resolved_template_dir_honors_an_explicit_config_value(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert (
        resolved_template_dir(build_config({"cv": {"template_dir": "my-templates"}}))
        == tmp_path / "my-templates"
    )
