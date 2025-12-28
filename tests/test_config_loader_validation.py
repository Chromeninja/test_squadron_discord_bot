"""
Config Loader Validation Tests

Tests for config loading, validation, defaults, and error handling.
Uses temp config files to test various scenarios.
"""

import os

from config.config_loader import ConfigLoader, normalize_prefix
from tests.factories.config_factories import (
    make_config,
    make_invalid_config,
    make_minimal_config,
    temp_config_file,
)


class TestConfigLoaderBasics:
    """Test basic config loading functionality."""

    def setup_method(self):
        """Reset ConfigLoader state before each test."""
        ConfigLoader.reset()

    def teardown_method(self):
        """Clean up after each test."""
        ConfigLoader.reset()
        # Clean up any env vars we may have set
        if "CONFIG_PATH" in os.environ:
            del os.environ["CONFIG_PATH"]

    def test_load_valid_config(self):
        """Test loading a valid configuration file."""
        config = make_config(bot_token="test_token_123", prefix="!")  # noqa: S106

        with temp_config_file(config) as path:
            result = ConfigLoader.load_config(path)

            assert result["token"] == "test_token_123"
            assert result["prefix"] == "!"

    def test_load_minimal_config(self):
        """Test loading minimal config with only required fields."""
        config = make_minimal_config()

        with temp_config_file(config) as path:
            result = ConfigLoader.load_config(path)

            assert result["token"] == "test_token"

    def test_config_status_ok_after_successful_load(self):
        """Test that config status is 'ok' after successful load."""
        config = make_config()

        with temp_config_file(config) as path:
            ConfigLoader.load_config(path)
            status = ConfigLoader.get_config_status()

            assert status["config_status"] == "ok"
            assert status["config_loaded"] is True
            assert status["config_path"] == path

    def test_get_returns_value_for_existing_key(self):
        """Test get() returns correct value for existing key."""
        config = make_config(bot_token="my_token")  # noqa: S106

        with temp_config_file(config) as path:
            ConfigLoader.load_config(path)

            assert ConfigLoader.get("token") == "my_token"

    def test_get_returns_default_for_missing_key(self):
        """Test get() returns default for missing key."""
        config = make_minimal_config()

        with temp_config_file(config) as path:
            ConfigLoader.load_config(path)

            assert ConfigLoader.get("nonexistent_key") is None
            assert ConfigLoader.get("nonexistent_key", "default_value") == "default_value"


class TestConfigLoaderMissingFile:
    """Test config loader handling of missing files."""

    def setup_method(self):
        ConfigLoader.reset()

    def teardown_method(self):
        ConfigLoader.reset()

    def test_missing_file_returns_empty_config(self):
        """Test that missing config file returns empty config."""
        result = ConfigLoader.load_config("/nonexistent/path/config.yaml")

        assert result == {}

    def test_missing_file_sets_degraded_status(self):
        """Test that missing file sets status to degraded."""
        ConfigLoader.load_config("/nonexistent/path/config.yaml")
        status = ConfigLoader.get_config_status()

        assert status["config_status"] == "degraded"

    def test_missing_file_sets_config_path(self):
        """Test that config path is still tracked for missing file."""
        path = "/nonexistent/path/config.yaml"
        ConfigLoader.load_config(path)
        status = ConfigLoader.get_config_status()

        assert status["config_path"] == path


class TestConfigLoaderInvalidYaml:
    """Test config loader handling of invalid YAML."""

    def setup_method(self):
        ConfigLoader.reset()

    def teardown_method(self):
        ConfigLoader.reset()

    def test_invalid_yaml_returns_empty_config(self):
        """Test that invalid YAML returns empty config."""
        with temp_config_file(content="invalid: yaml: content: [broken") as path:
            result = ConfigLoader.load_config(path)

            assert result == {}

    def test_invalid_yaml_sets_error_status(self):
        """Test that invalid YAML sets status to error."""
        with temp_config_file(content="invalid: yaml: content: [broken") as path:
            ConfigLoader.load_config(path)
            status = ConfigLoader.get_config_status()

            assert status["config_status"] == "error"

    def test_non_dict_yaml_returns_empty(self):
        """Test that YAML that isn't a dict returns empty config."""
        with temp_config_file(content="- just\n- a\n- list") as path:
            result = ConfigLoader.load_config(path)

            assert result == {}


class TestConfigLoaderDefaults:
    """Test default value handling."""

    def setup_method(self):
        ConfigLoader.reset()

    def teardown_method(self):
        ConfigLoader.reset()

    def test_default_logging_level_applied(self):
        """Test that invalid logging level defaults to INFO."""
        config = make_invalid_config("invalid_logging_level")

        with temp_config_file(config) as path:
            ConfigLoader.load_config(path)

            # After validation, should be corrected to INFO
            logging_config = ConfigLoader.get("logging", {})
            assert logging_config.get("level") == "INFO"

    def test_missing_logging_uses_default(self):
        """Test that missing logging config doesn't crash."""
        config = {"token": "test"}

        with temp_config_file(config) as path:
            result = ConfigLoader.load_config(path)

            # Should load without error
            assert result["token"] == "test"


class TestConfigLoaderReset:
    """Test config loader reset functionality."""

    def test_reset_clears_config(self):
        """Test that reset clears loaded config."""
        config = make_config(bot_token="loaded_token")  # noqa: S106

        with temp_config_file(config) as path:
            ConfigLoader.load_config(path)
            assert ConfigLoader.get("token") == "loaded_token"

            ConfigLoader.reset()

            status = ConfigLoader.get_config_status()
            assert status["config_status"] == "not_loaded"
            assert status["config_loaded"] is False
            assert status.get("config_path") is None
            assert ConfigLoader.get("token") is None

    def test_can_reload_after_reset(self):
        """Test that config can be reloaded after reset."""
        config1 = make_config(bot_token="first_token")  # noqa: S106
        config2 = make_config(bot_token="second_token")  # noqa: S106

        with temp_config_file(config1) as path1:
            ConfigLoader.load_config(path1)
            assert ConfigLoader.get("token") == "first_token"

            ConfigLoader.reset()

            with temp_config_file(config2) as path2:
                ConfigLoader.load_config(path2)
                assert ConfigLoader.get("token") == "second_token"


class TestPrefixNormalization:
    """Test command prefix normalization."""

    def test_none_prefix_returns_empty(self):
        """Test that None prefix returns empty list (mention-only)."""
        result, warnings = normalize_prefix(None)
        assert result == []
        assert len(warnings) == 0

    def test_empty_string_prefix_returns_empty(self):
        """Test that empty string returns empty list."""
        result, _warnings = normalize_prefix("")
        assert result == []

    def test_valid_string_prefix(self):
        """Test valid string prefix is normalized."""
        result, warnings = normalize_prefix("!")
        assert result == ["!"]
        assert len(warnings) == 0

    def test_valid_list_prefix(self):
        """Test valid list of prefixes."""
        result, warnings = normalize_prefix(["!", "?", "."])
        assert result == ["!", "?", "."]
        assert len(warnings) == 0

    def test_whitespace_only_prefix_ignored(self):
        """Test that whitespace-only prefix is ignored with warning."""
        result, _warnings = normalize_prefix("   ")
        assert result == []
        # Should have warning about whitespace

    def test_prefix_exceeding_max_length_truncated(self):
        """Test that overly long prefix is truncated."""
        long_prefix = "!" * 20  # Exceeds MAX_PREFIX_LENGTH (10)
        result, warnings = normalize_prefix(long_prefix)
        assert len(result) == 1
        assert len(result[0]) == 10  # Truncated to max
        assert len(warnings) > 0

    def test_prefix_count_limit_enforced(self):
        """Test that prefix count limit (5) is enforced."""
        many_prefixes = ["1", "2", "3", "4", "5", "6", "7"]
        result, warnings = normalize_prefix(many_prefixes)
        assert len(result) == 5  # MAX_PREFIX_COUNT
        assert len(warnings) > 0

    def test_duplicate_prefixes_deduplicated(self):
        """Test that duplicate prefixes are removed."""
        result, _warnings = normalize_prefix(["!", "!", "?", "!"])
        assert result == ["!", "?"]

    def test_non_ascii_prefix_rejected(self):
        """Test that non-ASCII prefixes are rejected."""
        result, warnings = normalize_prefix("🎮")
        assert result == []
        assert len(warnings) > 0

    def test_invalid_type_prefix_rejected(self):
        """Test that invalid type prefix is rejected."""
        result, warnings = normalize_prefix({"invalid": "dict"})
        assert result == []
        assert len(warnings) > 0

    def test_mixed_valid_invalid_list(self):
        """Test list with mix of valid and invalid items."""
        result, warnings = normalize_prefix(["!", 123, "?", None])
        assert "!" in result
        assert "?" in result
        assert len(result) == 2
        assert len(warnings) > 0  # Warnings for invalid items


class TestConfigEnvironmentOverride:
    """Test environment variable overrides."""

    def setup_method(self):
        ConfigLoader.reset()
        self._original_env = os.environ.get("CONFIG_PATH")

    def teardown_method(self):
        ConfigLoader.reset()
        if self._original_env is not None:
            os.environ["CONFIG_PATH"] = self._original_env
        elif "CONFIG_PATH" in os.environ:
            del os.environ["CONFIG_PATH"]

    def test_config_path_env_override(self):
        """Test that CONFIG_PATH env var overrides default path."""
        config = make_config(bot_token="env_override_token")  # noqa: S106

        with temp_config_file(config) as path:
            os.environ["CONFIG_PATH"] = path
            ConfigLoader.reset()

            result = ConfigLoader.load_config()  # No path argument

            assert result["token"] == "env_override_token"

    def test_explicit_path_overrides_env(self):
        """Test that explicit path argument overrides env var."""
        config1 = make_config(bot_token="env_token")  # noqa: S106
        config2 = make_config(bot_token="explicit_token")  # noqa: S106

        with temp_config_file(config1) as env_path:
            os.environ["CONFIG_PATH"] = env_path

            with temp_config_file(config2) as explicit_path:
                ConfigLoader.reset()
                result = ConfigLoader.load_config(explicit_path)

                assert result["token"] == "explicit_token"
