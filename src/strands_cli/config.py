"""Configuration management for Strands CLI.

Provides environment-based configuration using Pydantic Settings.
All settings can be overridden via environment variables with STRANDS_ prefix.

Example:
    export STRANDS_AWS_REGION=us-west-2
    export STRANDS_BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
    export STRANDS_LOG_LEVEL=DEBUG
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrandsConfig(BaseSettings):
    """Configuration settings for Strands CLI.

    Loads settings from environment variables (STRANDS_ prefix) and .env file.
    Settings cascade: .env file < environment variables < explicit overrides.

    Configuration Groups:
        AWS: Region and profile for Bedrock access
        Bedrock: Default model selection
        Workflow: Schema path for validation
        Cache: Enable/disable and directory configuration
        Observability: OTEL endpoint and logging preferences
    """

    model_config = SettingsConfigDict(
        env_prefix="STRANDS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # AWS Configuration
    aws_region: str = Field(default="us-east-1", description="AWS region")
    aws_profile: str | None = Field(default=None, description="AWS profile name")

    # Bedrock Configuration
    bedrock_model_id: str = Field(
        default="anthropic.claude-3-sonnet-20240229-v1:0",
        description="Bedrock model ID",
    )

    # Workflow Configuration
    workflow_schema_path: Path | None = Field(
        default=None,
        description="Path to workflow schema JSON file",
    )

    # Cache Configuration
    cache_enabled: bool = Field(default=True, description="Enable caching")
    cache_dir: Path | None = Field(default=None, description="Cache directory")

    # Observability
    otel_enabled: bool = Field(default=False, description="Enable OpenTelemetry")
    otel_endpoint: str | None = Field(
        default=None,
        description="OpenTelemetry collector endpoint",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="console", description="Log format (json or console)")

    # HTTP Security
    http_allowed_domains: list[str] = Field(
        default_factory=list,
        description="Allowed domain patterns for HTTP executors (regex)",
    )
    http_blocked_patterns: list[str] = Field(
        default_factory=list,
        description="Additional blocked URL patterns for HTTP executors (regex)",
    )
