"""Provider-specific client configuration for Bedrock and Ollama.

Adapts runtime configuration to provider-specific model clients using
the Strands Agents SDK. Each provider has different requirements:

Bedrock:
    - Requires AWS region configured via environment or ~/.aws/config
    - Model IDs follow AWS format (e.g., anthropic.claude-3-sonnet-...)
    - BedrockModel creates its own boto3 client internally

Ollama:
    - Requires host URL (e.g., http://localhost:11434)
    - Model IDs are local model names (e.g., gpt-oss, llama2)

Both providers support model_id override from runtime or agent config.
"""

import structlog
from strands.models.bedrock import BedrockModel
from strands.models.ollama import OllamaModel

from strands_cli.types import ProviderType, Runtime


class ProviderError(Exception):
    """Raised when provider configuration or initialization fails."""

    pass


def create_bedrock_model(runtime: Runtime) -> BedrockModel:
    """Create a Bedrock model client.

    Initializes AWS Bedrock runtime client using boto3 and wraps it
    with Strands BedrockModel adapter. Uses default AWS credential chain
    (environment variables, ~/.aws/credentials, instance role, etc.).

    Args:
        runtime: Runtime configuration with provider=bedrock

    Returns:
        Configured BedrockModel ready for agent creation

    Raises:
        ProviderError: If region is missing or client creation fails
    """
    logger = structlog.get_logger(__name__)

    if not runtime.region:
        raise ProviderError("Bedrock provider requires runtime.region")

    # Default model if not specified
    model_id = runtime.model_id or "us.anthropic.claude-3-sonnet-20240229-v1:0"

    logger.debug("creating_bedrock_model", region=runtime.region, model_id=model_id)

    # Create Strands BedrockModel
    # BedrockModel creates its own boto3 client internally using AWS credentials from environment
    try:
        model = BedrockModel(
            model_id=model_id,
            # Region is configured via AWS environment variables or ~/.aws/config
            # The SDK will use boto3.client() internally with the configured region
        )
    except Exception as e:
        raise ProviderError(f"Failed to create BedrockModel: {e}") from e

    return model


def create_ollama_model(runtime: Runtime) -> OllamaModel:
    """Create an Ollama model client.

    Initializes Ollama client pointing to specified host URL.
    Assumes Ollama server is running and accessible.

    Args:
        runtime: Runtime configuration with provider=ollama

    Returns:
        Configured OllamaModel ready for agent creation

    Raises:
        ProviderError: If host is missing or client creation fails
    """
    logger = structlog.get_logger(__name__)

    if not runtime.host:
        raise ProviderError("Ollama provider requires runtime.host")

    # Default model if not specified
    model_id = runtime.model_id or "gpt-oss"

    logger.debug("creating_ollama_client", host=runtime.host, model_id=model_id)

    # Create Strands Ollama model
    try:
        model = OllamaModel(
            host=runtime.host,
            model_id=model_id,
        )
    except Exception as e:
        raise ProviderError(f"Failed to create OllamaModel: {e}") from e

    return model


def create_model(runtime: Runtime) -> BedrockModel | OllamaModel:
    """Create a model client based on the provider.

    Args:
        runtime: Runtime configuration

    Returns:
        Strands model (BedrockModel or OllamaModel)

    Raises:
        ProviderError: If provider is unsupported or configuration is invalid
    """
    if runtime.provider == ProviderType.BEDROCK:
        return create_bedrock_model(runtime)
    elif runtime.provider == ProviderType.OLLAMA:
        return create_ollama_model(runtime)
    else:
        raise ProviderError(f"Unsupported provider: {runtime.provider}. Use 'bedrock' or 'ollama'.")
