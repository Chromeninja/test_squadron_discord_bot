"""
Unit tests for production guardrails.

Tests the validation logic for production environment checks including
DISCORD_TOKEN validation and config file verification.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.production_guardrails import (
    ProductionGuardrailError,
    _get_file_hash,
    _get_file_size,
    run_production_guardrails,
    validate_config_files,
    validate_discord_token,
)


class TestDiscordTokenValidation:
    """Tests for DISCORD_TOKEN validation."""

    def test_missing_token_raises_error(self):
        """Test that missing DISCORD_TOKEN raises ProductionGuardrailError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ProductionGuardrailError) as exc_info:
                validate_discord_token()
            assert "DISCORD_TOKEN environment variable is not set" in str(exc_info.value)

    def test_empty_token_raises_error(self):
        """Test that empty DISCORD_TOKEN raises ProductionGuardrailError."""
        with patch.dict(os.environ, {"DISCORD_TOKEN": ""}):
            with pytest.raises(ProductionGuardrailError) as exc_info:
                validate_discord_token()
            assert "DISCORD_TOKEN environment variable is empty" in str(exc_info.value)

    def test_whitespace_only_token_raises_error(self):
        """Test that whitespace-only DISCORD_TOKEN raises ProductionGuardrailError."""
        with patch.dict(os.environ, {"DISCORD_TOKEN": "   \n\t  "}):
            with pytest.raises(ProductionGuardrailError) as exc_info:
                validate_discord_token()
            assert "DISCORD_TOKEN environment variable is empty" in str(exc_info.value)

    @pytest.mark.parametrize("placeholder", [
        "YOUR_BOT_TOKEN_HERE",
        "your_bot_token",
        "placeholder_token",
        "change_me",
        "CHANGE_ME",
        "example_token",
        "test_token",
        "None",
        "null",
    ])
    def test_placeholder_tokens_raise_error(self, placeholder):
        """Test that placeholder tokens raise ProductionGuardrailError."""
        with patch.dict(os.environ, {"DISCORD_TOKEN": placeholder}):
            with pytest.raises(ProductionGuardrailError) as exc_info:
                validate_discord_token()
            assert "appears to be a placeholder value" in str(exc_info.value)

    def test_short_token_raises_error(self):
        """Test that suspiciously short tokens raise ProductionGuardrailError."""
        with patch.dict(os.environ, {"DISCORD_TOKEN": "short"}):
            with pytest.raises(ProductionGuardrailError) as exc_info:
                validate_discord_token()
            assert "appears to be invalid (too short" in str(exc_info.value)

    def test_valid_token_passes(self):
        """Test that a valid-looking token passes validation."""
        # Discord bot tokens are typically 59+ characters, mix of letters, numbers, and some symbols
    valid_token = "DUMMY_DISCORD_TOKEN_FOR_TESTS_ONLY_DO_NOT_USE_IN_PRODUCTION"
    with patch.dict(os.environ, {"DISCORD_TOKEN": valid_token}):
            # Should not raise any exception
            validate_discord_token()


class TestConfigFileValidation:
    """Tests for config file validation."""

    def test_missing_config_file_raises_error(self):
        """Test that missing config.yaml raises ProductionGuardrailError."""
        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = False
            with pytest.raises(ProductionGuardrailError) as exc_info:
                validate_config_files()
            assert "Configuration file not found" in str(exc_info.value)

    def test_config_exists_example_missing_passes(self):
        """Test that config.yaml existing without example file passes with warning."""
        def mock_exists(self):
            return str(self).endswith("config.yaml")

        with patch.object(Path, 'exists', mock_exists):
            # Should not raise exception (just logs warning)
            validate_config_files()

    def test_identical_config_files_raise_error(self):
        """Test that identical config.yaml and config-example.yaml raise error."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("utils.production_guardrails._get_file_size") as mock_size, \
             patch("utils.production_guardrails._get_file_hash") as mock_hash:

            # Same size and hash indicates identical files
            mock_size.return_value = 1000
            mock_hash.return_value = "abc123def456"

            with pytest.raises(ProductionGuardrailError) as exc_info:
                validate_config_files()
            assert "is identical to" in str(exc_info.value)

    def test_different_config_files_pass(self):
        """Test that different config files pass validation."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("utils.production_guardrails._get_file_size") as mock_size:

            # Different sizes indicate different files
            mock_size.side_effect = [1000, 1200]  # config.yaml, config-example.yaml

            # Should not raise exception
            validate_config_files()

    def test_same_size_different_hash_passes(self):
        """Test that files with same size but different content pass."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("utils.production_guardrails._get_file_size", return_value=1000), \
             patch("utils.production_guardrails._get_file_hash") as mock_hash:

            # Same size but different hashes
            mock_hash.side_effect = ["abc123", "def456"]

            # Should not raise exception
            validate_config_files()


class TestProductionGuardrails:
    """Tests for the main production guardrails runner."""

    def test_non_production_environment_skips_checks(self, caplog):
        """Test that non-production environments skip guardrail checks."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            run_production_guardrails()
            assert "skipping production guardrails" in caplog.text

    def test_missing_environment_skips_checks(self, caplog):
        """Test that missing ENVIRONMENT variable skips guardrail checks."""
        with patch.dict(os.environ, {}, clear=True):
            run_production_guardrails()
            assert "skipping production guardrails" in caplog.text

    def test_production_environment_runs_checks(self):
        """Test that production environment runs all checks."""
    valid_token = "DUMMY_DISCORD_TOKEN_FOR_TESTS_ONLY_DO_NOT_USE_IN_PRODUCTION"

        with patch.dict(os.environ, {
                "ENVIRONMENT": "production",
                "DISCORD_TOKEN": valid_token
            }), \
            patch("pathlib.Path.exists", return_value=True), \
            patch("utils.production_guardrails._get_file_size") as mock_size:
            # Different file sizes to pass config validation
            mock_size.side_effect = [1000, 1200]
            # Should not raise exception or exit
            run_production_guardrails()

    def test_production_environment_with_errors_exits(self):
        """Test that production environment with errors calls sys.exit(1)."""
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "DISCORD_TOKEN": "invalid_token"  # Too short, will fail validation
        }), \
        pytest.raises(SystemExit) as exc_info:
            run_production_guardrails()

        assert exc_info.value.code == 1

    def test_case_insensitive_production_environment(self):
        """Test that ENVIRONMENT check is case-insensitive."""
    valid_token = "DUMMY_DISCORD_TOKEN_FOR_TESTS_ONLY_DO_NOT_USE_IN_PRODUCTION"

        for env_value in ["PRODUCTION", "Production", "production"]:
            with patch.dict(os.environ, {
                "ENVIRONMENT": env_value,
                "DISCORD_TOKEN": valid_token
            }), \
            patch("pathlib.Path.exists", return_value=True), \
            patch("utils.production_guardrails._get_file_size") as mock_size:
                mock_size.side_effect = [1000, 1200]
                # Should not raise exception or exit
                run_production_guardrails()


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_get_file_hash_nonexistent_file(self):
        """Test that _get_file_hash returns None for nonexistent files."""
        result = _get_file_hash(Path("/nonexistent/file"))
        assert result is None

    def test_get_file_hash_existing_file(self):
        """Test that _get_file_hash returns hash for existing files."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            f.flush()

            result = _get_file_hash(Path(f.name))
            assert result is not None
            assert len(result) == 64  # SHA-256 hex digest length

            # Clean up
            os.unlink(f.name)

    def test_get_file_size_nonexistent_file(self):
        """Test that _get_file_size returns None for nonexistent files."""
        result = _get_file_size(Path("/nonexistent/file"))
        assert result is None

    def test_get_file_size_existing_file(self):
        """Test that _get_file_size returns size for existing files."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            content = "test content"
            f.write(content)
            f.flush()

            result = _get_file_size(Path(f.name))
            assert result == len(content.encode('utf-8'))

            # Clean up
            os.unlink(f.name)
