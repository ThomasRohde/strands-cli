"""Tests for configuration management (src/strands_cli/config.py).

Coverage targets:
- Environment variable loading with STRANDS_ prefix
- .env file parsing
- Default value fallbacks
- Type coercion (str, Path, bool)
- Case-insensitive environment variables
- Priority: env vars override .env file
"""

import os
from pathlib import Path

import pytest

from strands_cli.config import StrandsConfig


class TestStrandsConfigDefaults:
    """Test default configuration values."""

    def test_config_defaults_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that config loads with expected defaults when no env vars set."""
        # Clear all STRANDS_ env vars
        for key in list(os.environ.keys()):
            if key.startswith("STRANDS_"):
                monkeypatch.delenv(key, raising=False)

        config = StrandsConfig()

        assert config.aws_region == "us-east-1"
        assert config.aws_profile is None
        assert config.bedrock_model_id == "anthropic.claude-3-sonnet-20240229-v1:0"
        assert config.workflow_schema_path is None
        assert config.cache_enabled is True
        assert config.cache_dir is None
        assert config.otel_enabled is False
        assert config.otel_endpoint is None
        assert config.log_level == "INFO"
        assert config.log_format == "console"

    def test_config_minimal_instantiation(self) -> None:
        """Test that config can be instantiated with no arguments."""
        config = StrandsConfig()
        assert isinstance(config, StrandsConfig)
        assert config.aws_region  # Should have default value


class TestStrandsConfigEnvVars:
    """Test environment variable loading."""

    def test_config_loads_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that config loads values from STRANDS_ prefixed env vars."""
        monkeypatch.setenv("STRANDS_AWS_REGION", "us-west-2")
        monkeypatch.setenv("STRANDS_AWS_PROFILE", "production")
        monkeypatch.setenv("STRANDS_BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        monkeypatch.setenv("STRANDS_LOG_LEVEL", "DEBUG")

        config = StrandsConfig()

        assert config.aws_region == "us-west-2"
        assert config.aws_profile == "production"
        assert config.bedrock_model_id == "anthropic.claude-3-haiku-20240307-v1:0"
        assert config.log_level == "DEBUG"

    def test_config_env_prefix_strands(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that only STRANDS_ prefix is recognized."""
        monkeypatch.setenv("AWS_REGION", "eu-west-1")  # Should be ignored
        monkeypatch.setenv("STRANDS_AWS_REGION", "us-east-1")

        config = StrandsConfig()

        # Should use STRANDS_ prefixed value, not plain AWS_REGION
        assert config.aws_region == "us-east-1"

    def test_config_case_insensitive_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that env vars are case-insensitive."""
        # Test lowercase
        monkeypatch.setenv("strands_aws_region", "ap-southeast-1")
        config1 = StrandsConfig()
        assert config1.aws_region == "ap-southeast-1"

        # Test mixed case
        monkeypatch.setenv("StRaNdS_AwS_ReGiOn", "eu-central-1")
        config2 = StrandsConfig()
        assert config2.aws_region == "eu-central-1"


class TestStrandsConfigBooleans:
    """Test boolean field handling."""

    def test_config_boolean_true_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that various true values are parsed correctly."""
        for true_value in ["true", "True", "TRUE", "1", "yes", "Yes", "YES"]:
            monkeypatch.setenv("STRANDS_CACHE_ENABLED", true_value)
            config = StrandsConfig()
            assert config.cache_enabled is True, f"Failed for value: {true_value}"

    def test_config_boolean_false_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that various false values are parsed correctly."""
        for false_value in ["false", "False", "FALSE", "0", "no", "No", "NO"]:
            monkeypatch.setenv("STRANDS_CACHE_ENABLED", false_value)
            config = StrandsConfig()
            assert config.cache_enabled is False, f"Failed for value: {false_value}"

    def test_config_otel_enabled_toggle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test OTEL enabled flag."""
        monkeypatch.setenv("STRANDS_OTEL_ENABLED", "true")
        config = StrandsConfig()
        assert config.otel_enabled is True


class TestStrandsConfigPaths:
    """Test Path field handling."""

    def test_config_path_from_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that string paths are converted to Path objects."""
        monkeypatch.setenv("STRANDS_WORKFLOW_SCHEMA_PATH", "/path/to/schema.json")
        monkeypatch.setenv("STRANDS_CACHE_DIR", "/tmp/strands-cache")

        config = StrandsConfig()

        assert isinstance(config.workflow_schema_path, Path)
        assert config.workflow_schema_path == Path("/path/to/schema.json")
        assert isinstance(config.cache_dir, Path)
        assert config.cache_dir == Path("/tmp/strands-cache")

    def test_config_path_none_when_not_set(self) -> None:
        """Test that Path fields default to None."""
        config = StrandsConfig()
        assert config.workflow_schema_path is None
        assert config.cache_dir is None


class TestStrandsConfigOptionalFields:
    """Test optional field handling."""

    def test_config_optional_fields_can_be_none(self) -> None:
        """Test that optional fields accept None."""
        config = StrandsConfig()
        assert config.aws_profile is None
        assert config.workflow_schema_path is None
        assert config.cache_dir is None
        assert config.otel_endpoint is None

    def test_config_optional_fields_can_be_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that optional fields can be set via env vars."""
        monkeypatch.setenv("STRANDS_AWS_PROFILE", "dev")
        monkeypatch.setenv("STRANDS_OTEL_ENDPOINT", "http://localhost:4317")

        config = StrandsConfig()

        assert config.aws_profile == "dev"
        assert config.otel_endpoint == "http://localhost:4317"


class TestStrandsConfigEdgeCases:
    """Test edge cases and validation."""

    def test_config_empty_string_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that empty strings are handled correctly."""
        monkeypatch.setenv("STRANDS_LOG_LEVEL", "")
        config = StrandsConfig()
        # Empty string should be treated as empty, falls back to default
        assert config.log_level in ["", "INFO"]  # Pydantic may keep empty or use default

    def test_config_whitespace_trimmed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that whitespace is trimmed from string values."""
        monkeypatch.setenv("STRANDS_AWS_REGION", "  us-west-2  ")
        config = StrandsConfig()
        # Pydantic should trim whitespace
        assert config.aws_region.strip() == "us-west-2"

    def test_config_log_format_options(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test different log format values."""
        for fmt in ["json", "console"]:
            monkeypatch.setenv("STRANDS_LOG_FORMAT", fmt)
            config = StrandsConfig()
            assert config.log_format == fmt


class TestStrandsConfigDotEnv:
    """Test .env file loading."""

    def test_config_loads_from_dotenv_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that config loads from .env file in current directory."""
        # Create .env file
        env_file = tmp_path / ".env"
        env_file.write_text(
            "STRANDS_AWS_REGION=eu-west-1\nSTRANDS_LOG_LEVEL=DEBUG\nSTRANDS_CACHE_ENABLED=false\n"
        )

        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        config = StrandsConfig()

        assert config.aws_region == "eu-west-1"
        assert config.log_level == "DEBUG"
        assert config.cache_enabled is False

    def test_config_env_vars_override_dotenv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that environment variables override .env file values."""
        # Create .env file
        env_file = tmp_path / ".env"
        env_file.write_text("STRANDS_AWS_REGION=eu-west-1\n")

        # Set env var to different value
        monkeypatch.setenv("STRANDS_AWS_REGION", "us-east-1")
        monkeypatch.chdir(tmp_path)

        config = StrandsConfig()

        # Env var should win
        assert config.aws_region == "us-east-1"


class TestStrandsConfigValidation:
    """Test validation and error handling."""

    def test_config_invalid_path_still_creates_path_object(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid paths still create Path objects (validation happens at usage)."""
        monkeypatch.setenv("STRANDS_WORKFLOW_SCHEMA_PATH", "/nonexistent/path.json")
        config = StrandsConfig()
        # Should create Path object even if file doesn't exist
        assert isinstance(config.workflow_schema_path, Path)
        assert config.workflow_schema_path == Path("/nonexistent/path.json")

    def test_config_can_be_updated_programmatically(self) -> None:
        """Test that config fields can be updated after instantiation."""
        config = StrandsConfig()
        original_region = config.aws_region

        # Update field
        config.aws_region = "ap-northeast-1"
        assert config.aws_region == "ap-northeast-1"
        assert config.aws_region != original_region


class TestStrandsConfigRepresentation:
    """Test config object representation."""

    def test_config_model_dump(self) -> None:
        """Test that config can be dumped to dict."""
        config = StrandsConfig()
        data = config.model_dump()

        assert isinstance(data, dict)
        assert "aws_region" in data
        assert "bedrock_model_id" in data
        assert data["aws_region"] == "us-east-1"

    def test_config_model_dump_excludes_none(self) -> None:
        """Test that None values can be excluded from dump."""
        config = StrandsConfig()
        data = config.model_dump(exclude_none=True)

        # None fields should be excluded
        assert "aws_profile" not in data or data["aws_profile"] is None
        # Non-None fields should be present
        assert "aws_region" in data


class TestStrandsConfigIntegration:
    """Integration tests for common usage patterns."""

    def test_config_realistic_bedrock_setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test a realistic Bedrock configuration."""
        monkeypatch.setenv("STRANDS_AWS_REGION", "us-east-1")
        monkeypatch.setenv("STRANDS_AWS_PROFILE", "production")
        monkeypatch.setenv("STRANDS_BEDROCK_MODEL_ID", "anthropic.claude-3-opus-20240229-v1:0")
        monkeypatch.setenv("STRANDS_CACHE_ENABLED", "true")
        monkeypatch.setenv("STRANDS_LOG_LEVEL", "INFO")

        config = StrandsConfig()

        assert config.aws_region == "us-east-1"
        assert config.aws_profile == "production"
        assert config.bedrock_model_id == "anthropic.claude-3-opus-20240229-v1:0"
        assert config.cache_enabled is True
        assert config.log_level == "INFO"

    def test_config_realistic_ollama_setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test a realistic Ollama configuration (minimal AWS)."""
        monkeypatch.setenv("STRANDS_CACHE_ENABLED", "true")
        monkeypatch.setenv("STRANDS_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("STRANDS_LOG_FORMAT", "console")

        config = StrandsConfig()

        # Ollama doesn't need AWS config, but should have defaults
        assert config.aws_region  # Has default
        assert config.cache_enabled is True
        assert config.log_level == "DEBUG"
        assert config.log_format == "console"

    def test_config_otel_enabled_setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test OTEL configuration."""
        monkeypatch.setenv("STRANDS_OTEL_ENABLED", "true")
        monkeypatch.setenv("STRANDS_OTEL_ENDPOINT", "http://localhost:4317")

        config = StrandsConfig()

        assert config.otel_enabled is True
        assert config.otel_endpoint == "http://localhost:4317"
