from pathlib import Path

import pytest

from config.config_loader import ConfigLoader


@pytest.fixture(autouse=True)
def reset_config_loader():
    """Ensure ConfigLoader state does not leak between tests."""
    ConfigLoader.reset()
    yield
    ConfigLoader.reset()


def test_config_loader_respects_config_path_override(monkeypatch, tmp_path):
    custom_path = tmp_path / "custom-config.yaml"
    custom_path.write_text("""logging:\n  level: DEBUG\ncustom: true\n""", encoding="utf-8")

    monkeypatch.setenv("CONFIG_PATH", str(custom_path))

    config = ConfigLoader.load_config()
    status = ConfigLoader.get_config_status()

    assert config.get("logging", {}).get("level") == "DEBUG"
    assert status["config_path"] == str(custom_path)
    assert status["config_status"] == "ok"


def test_config_loader_resolves_default_from_any_cwd(monkeypatch, tmp_path):
    # Change working directory to ensure loader uses its own path resolution
    nested = tmp_path / "deep" / "nested"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.delenv("CONFIG_PATH", raising=False)

    config = ConfigLoader.load_config()
    status = ConfigLoader.get_config_status()

    expected_path = Path(__file__).resolve().parents[3] / "config" / "config.yaml"
    assert status["config_path"] == str(expected_path)
    assert config, "Default config should load even from nested working directories"


def test_config_loader_status_error_on_invalid_yaml(monkeypatch, tmp_path):
    broken = tmp_path / "broken.yaml"
    broken.write_text("voice: [unclosed\n", encoding="utf-8")

    monkeypatch.setenv("CONFIG_PATH", str(broken))

    config = ConfigLoader.load_config()
    status = ConfigLoader.get_config_status()

    assert config == {}
    assert status["config_status"] == "error"
    assert status["config_path"] == str(broken)


def test_config_loader_status_degraded_on_missing(monkeypatch, tmp_path):
    missing = tmp_path / "missing.yaml"
    monkeypatch.setenv("CONFIG_PATH", str(missing))

    ConfigLoader.load_config()
    status = ConfigLoader.get_config_status()

    assert status["config_status"] == "degraded"
    assert status["config_path"] == str(missing)
