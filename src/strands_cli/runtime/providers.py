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

Performance Optimization:
    - Model clients are cached using functools.lru_cache with maxsize=16
    - This prevents redundant client creation in multi-step workflows
    - Cache is keyed by (provider, model_id, region, host) tuple
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Union

import structlog
from strands.models.bedrock import BedrockModel
from strands.models.ollama import OllamaModel
from strands.models.openai import OpenAIModel

from strands_cli.types import ProviderType, Runtime

if TYPE_CHECKING:
    from strands.models.anthropic import AnthropicModel
    from strands.models.gemini import GeminiModel


class ProviderError(Exception):
    """Raised when provider configuration or initialization fails."""

    pass


@dataclass(frozen=True)
class RuntimeConfig:
    """Hashable runtime configuration for LRU cache key.

    Frozen dataclass containing only the fields needed to uniquely identify
    a model client configuration. Used as the cache key for _create_model_cached.

    Attributes:
        provider: Provider type (bedrock, ollama, openai)
        model_id: Specific model identifier (or None for defaults)
        region: AWS region (Bedrock only)
        host: Host URL (Ollama/OpenAI only)
        temperature: Sampling temperature (OpenAI only)
        top_p: Nucleus sampling parameter (OpenAI only)
        max_tokens: Maximum tokens to generate (OpenAI only)
    """

    provider: str
    model_id: str | None
    region: str | None
    host: str | None
    temperature: float | None
    top_p: float | None
    max_tokens: int | None


def create_bedrock_model(runtime: Runtime) -> BedrockModel:
    """Create a Bedrock model client.

    Initializes AWS Bedrock runtime client using boto3 and wraps it
    with Strands BedrockModel adapter. Uses default AWS credential chain
    (environment variables, ~/.aws/credentials, instance role, etc.).

    Note: Inference parameters (temperature, top_p, max_tokens) are not
    currently supported due to Strands SDK limitations. The BedrockModel
    constructor does not accept a params argument. Parameters will be
    logged as warnings if present.

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

    # Warn if inference parameters are set but will be ignored
    # SDK limitation: BedrockModel does not accept params argument
    ignored_params = []
    if runtime.temperature is not None:
        ignored_params.append(f"temperature={runtime.temperature}")
    if runtime.top_p is not None:
        ignored_params.append(f"top_p={runtime.top_p}")
    if runtime.max_tokens is not None:
        ignored_params.append(f"max_tokens={runtime.max_tokens}")

    if ignored_params:
        logger.warning(
            "bedrock_inference_unsupported",
            message="Inference parameters not supported by Bedrock provider (SDK limitation)",
            ignored_params=ignored_params,
            model_id=model_id,
            workaround="Configure model inference via AWS Bedrock console or use OpenAI provider",
        )

    logger.debug("creating_bedrock_model", region=runtime.region, model_id=model_id)

    # Create Strands BedrockModel
    # BedrockModel creates its own boto3 client internally using AWS credentials from environment
    # SDK limitation: Cannot pass inference params (temperature, top_p, max_tokens)
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

    Note: Inference parameters (temperature, top_p, max_tokens) are not
    supported by Ollama provider. The OllamaModel constructor does not
    accept generation parameters. Configure these settings via Ollama
    model configuration files (Modelfile) instead.

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

    # Warn if inference parameters are set but will be ignored
    # SDK limitation: OllamaModel does not accept generation parameters
    ignored_params = []
    if runtime.temperature is not None:
        ignored_params.append(f"temperature={runtime.temperature}")
    if runtime.top_p is not None:
        ignored_params.append(f"top_p={runtime.top_p}")
    if runtime.max_tokens is not None:
        ignored_params.append(f"max_tokens={runtime.max_tokens}")

    if ignored_params:
        logger.warning(
            "ollama_inference_unsupported",
            message="Inference parameters not supported by Ollama provider",
            ignored_params=ignored_params,
            model_id=model_id,
            workaround="Configure temperature/sampling in Ollama Modelfile or use OpenAI provider",
        )

    logger.debug("creating_ollama_client", host=runtime.host, model_id=model_id)

    # Create Strands Ollama model
    # SDK limitation: Cannot pass inference params (temperature, top_p, max_tokens)
    try:
        model = OllamaModel(
            host=runtime.host,
            model_id=model_id,
        )
    except Exception as e:
        raise ProviderError(f"Failed to create OllamaModel: {e}") from e

    return model


def create_openai_model(runtime: Runtime) -> OpenAIModel:
    """Create an OpenAI model client.

    Initializes OpenAI client using API key from environment.
    Supports optional base_url for OpenAI-compatible servers.

    Args:
        runtime: Runtime configuration with provider=openai

    Returns:
        Configured OpenAIModel ready for agent creation

    Raises:
        ProviderError: If API key is missing or client creation fails
    """
    logger = structlog.get_logger(__name__)

    # Check for API key in environment
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ProviderError(
            "OpenAI provider requires OPENAI_API_KEY environment variable. "
            "Set it with: export OPENAI_API_KEY=your-api-key"
        )

    # Default model if not specified
    model_id = runtime.model_id or "gpt-4o-mini"

    # Build client_args with API key
    client_args = {"api_key": api_key}

    # Optional: support base_url for OpenAI-compatible servers
    if runtime.host:
        client_args["base_url"] = runtime.host
        logger.debug(
            "creating_openai_model",
            model_id=model_id,
            base_url=runtime.host,
        )
    else:
        logger.debug("creating_openai_model", model_id=model_id)

    # Build inference params from runtime configuration
    params = {}
    if runtime.temperature is not None:
        params["temperature"] = runtime.temperature
    if runtime.max_tokens is not None:
        params["max_tokens"] = runtime.max_tokens
    if runtime.top_p is not None:
        params["top_p"] = runtime.top_p

    # Create Strands OpenAI model
    try:
        if params:
            model = OpenAIModel(
                client_args=client_args,
                model_id=model_id,
                params=params,
            )
        else:
            model = OpenAIModel(
                client_args=client_args,
                model_id=model_id,
            )
    except Exception as e:
        raise ProviderError(f"Failed to create OpenAIModel: {e}") from e

    return model


def create_anthropic_model(runtime: Runtime) -> "AnthropicModel":
    """Create an Anthropic model client.

    Initializes Anthropic client using API key from environment.
    Supports Claude models with configurable inference parameters.

    Args:
        runtime: Runtime configuration with provider=anthropic

    Returns:
        Configured AnthropicModel ready for agent creation

    Raises:
        ProviderError: If API key is missing or client creation fails
    """
    logger = structlog.get_logger(__name__)

    try:
        from strands.models.anthropic import AnthropicModel
    except ImportError as e:
        raise ProviderError(
            "Anthropic provider requires 'strands-agents[anthropic]' to be installed. "
            "Install it with: uv pip install 'strands-agents[anthropic]'"
        ) from e

    # Check for API key in environment
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ProviderError(
            "Anthropic provider requires ANTHROPIC_API_KEY environment variable. "
            "Set it with: export ANTHROPIC_API_KEY=your-api-key"
        )

    # Default model if not specified
    model_id = runtime.model_id or "claude-sonnet-4-20250514"

    # Build client_args with API key
    client_args = {"api_key": api_key}

    logger.debug("creating_anthropic_model", model_id=model_id)

    # Build inference params from runtime configuration
    params = {}
    if runtime.temperature is not None:
        params["temperature"] = runtime.temperature
    if runtime.top_p is not None:
        params["top_p"] = runtime.top_p

    # max_tokens is required for Anthropic
    max_tokens = runtime.max_tokens if runtime.max_tokens is not None else 1024

    # Create Strands Anthropic model
    try:
        if params:
            model = AnthropicModel(
                client_args=client_args,
                model_id=model_id,
                max_tokens=max_tokens,
                params=params,
            )
        else:
            model = AnthropicModel(
                client_args=client_args,
                model_id=model_id,
                max_tokens=max_tokens,
            )
    except Exception as e:
        raise ProviderError(f"Failed to create AnthropicModel: {e}") from e

    return model


def create_gemini_model(runtime: Runtime) -> "GeminiModel":
    """Create a Gemini model client.

    Initializes Google Gemini client using API key from environment.
    Supports Gemini models with configurable inference parameters.

    Args:
        runtime: Runtime configuration with provider=gemini

    Returns:
        Configured GeminiModel ready for agent creation

    Raises:
        ProviderError: If API key is missing or client creation fails
    """
    logger = structlog.get_logger(__name__)

    try:
        from strands.models.gemini import GeminiModel
    except ImportError as e:
        raise ProviderError(
            "Gemini provider requires 'strands-agents[gemini]' to be installed. "
            "Install it with: uv pip install 'strands-agents[gemini]'"
        ) from e

    # Check for API key in environment (try both GOOGLE_API_KEY and GEMINI_API_KEY)
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ProviderError(
            "Gemini provider requires GOOGLE_API_KEY or GEMINI_API_KEY environment variable. "
            "Set it with: export GOOGLE_API_KEY=your-api-key (or GEMINI_API_KEY=your-api-key)"
        )

    # Default model if not specified
    model_id = runtime.model_id or "gemini-2.5-flash"

    # Build client_args with API key
    client_args = {"api_key": api_key}

    logger.debug("creating_gemini_model", model_id=model_id)

    # Build inference params from runtime configuration
    params = {}
    if runtime.temperature is not None:
        params["temperature"] = runtime.temperature
    if runtime.max_tokens is not None:
        params["max_output_tokens"] = runtime.max_tokens
    if runtime.top_p is not None:
        params["top_p"] = runtime.top_p

    # Create Strands Gemini model
    try:
        if params:
            model = GeminiModel(
                client_args=client_args,
                model_id=model_id,
                params=params,
            )
        else:
            model = GeminiModel(
                client_args=client_args,
                model_id=model_id,
            )
    except Exception as e:
        raise ProviderError(f"Failed to create GeminiModel: {e}") from e

    return model


@lru_cache(maxsize=16)
def _create_model_cached(
    config: RuntimeConfig,
) -> Union[BedrockModel, OllamaModel, OpenAIModel, "AnthropicModel", "GeminiModel"]:
    """Create a model client with LRU caching.

    This cached version prevents redundant model client creation in multi-step
    workflows. The cache is keyed by RuntimeConfig which contains all fields
    that uniquely identify a model configuration.

    Cache performance can be monitored via _create_model_cached.cache_info()
    which returns CacheInfo(hits, misses, maxsize, currsize).

    Args:
        config: Frozen RuntimeConfig containing provider, model_id, region, host, etc.

    Returns:
        Cached or newly created model client

    Raises:
        ProviderError: If provider is unsupported or configuration is invalid
    """
    logger = structlog.get_logger(__name__)

    # Reconstruct Runtime object from config for provider functions
    # Note: We only include fields that affect model creation, not execution policies
    try:
        provider_enum = ProviderType(config.provider)
    except ValueError as e:
        raise ProviderError(
            f"Unsupported provider: {config.provider}. "
            f"Use 'bedrock', 'ollama', 'openai', 'anthropic', or 'gemini'."
        ) from e

    runtime = Runtime(
        provider=provider_enum,
        model_id=config.model_id,
        region=config.region,
        host=config.host,
        temperature=config.temperature,
        top_p=config.top_p,
        max_tokens=config.max_tokens,
    )

    logger.debug(
        "creating_model_client",
        provider=config.provider,
        model_id=config.model_id,
        region=config.region,
        host=config.host,
    )

    if runtime.provider == ProviderType.BEDROCK:
        return create_bedrock_model(runtime)
    elif runtime.provider == ProviderType.OLLAMA:
        return create_ollama_model(runtime)
    elif runtime.provider == ProviderType.OPENAI:
        return create_openai_model(runtime)
    elif runtime.provider == ProviderType.ANTHROPIC:
        return create_anthropic_model(runtime)
    elif runtime.provider == ProviderType.GEMINI:
        return create_gemini_model(runtime)
    else:
        raise ProviderError(
            f"Unsupported provider: {runtime.provider}. "
            f"Use 'bedrock', 'ollama', 'openai', 'anthropic', or 'gemini'."
        )


def create_model(
    runtime: Runtime,
) -> Union[BedrockModel, OllamaModel, OpenAIModel, "AnthropicModel", "GeminiModel"]:
    """Create a model client based on the provider.

    This function converts the Runtime object to a hashable RuntimeConfig
    and delegates to the cached _create_model_cached function. This enables
    model client reuse across multiple agent builds in multi-step workflows.

    Cache statistics are logged periodically for observability.

    Args:
        runtime: Runtime configuration

    Returns:
        Strands model (BedrockModel, OllamaModel, OpenAIModel, AnthropicModel, or GeminiModel)

    Raises:
        ProviderError: If provider is unsupported or configuration is invalid
    """
    logger = structlog.get_logger(__name__)

    # Convert Runtime to hashable RuntimeConfig for caching
    config = RuntimeConfig(
        provider=runtime.provider.value,
        model_id=runtime.model_id,
        region=runtime.region,
        host=runtime.host,
        temperature=runtime.temperature,
        top_p=runtime.top_p,
        max_tokens=runtime.max_tokens,
    )

    # Call cached function
    model = _create_model_cached(config)

    # Log cache performance (every 10 calls to avoid spam)
    cache_info = _create_model_cached.cache_info()
    total_calls = cache_info.hits + cache_info.misses
    if total_calls > 0 and total_calls % 10 == 0:
        hit_rate = cache_info.hits / total_calls if total_calls > 0 else 0
        logger.info(
            "model_cache_stats",
            hits=cache_info.hits,
            misses=cache_info.misses,
            hit_rate=f"{hit_rate:.1%}",
            size=cache_info.currsize,
            maxsize=cache_info.maxsize,
        )

    return model
