"""Artifact output file management.

Handles writing workflow execution outputs to files using template rendering.
Supports Jinja2 templates for dynamic artifact content generation.

Features:
    - Template rendering with {{ last_response }}, {{ TRACE }}, and other variables
    - Directory creation (parents created automatically)
    - Overwrite protection (--force flag required)
    - Error handling for I/O failures
    - UTF-8 encoding
    - Path sanitization to prevent traversal attacks

Artifact Templates:
    Current: {{ last_response }} - final agent output
             {{ TRACE }} - complete trace JSON with spans and metadata
    Future: {{ PROVENANCE }}, etc.
"""

import json
import re
from pathlib import Path
from typing import Any

import structlog

from strands_cli.loader import render_template
from strands_cli.telemetry import get_trace_collector

logger = structlog.get_logger(__name__)


class ArtifactError(Exception):
    """Raised when artifact writing fails."""

    pass


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """Sanitize a filename to prevent path traversal and filesystem issues.

    Removes path separators, special characters, and limits length.
    Ensures the resulting filename is safe for all platforms.

    Args:
        filename: Raw filename (may contain unsafe characters)
        max_length: Maximum length of output (default: 100)

    Returns:
        Sanitized filename safe for filesystem use

    Examples:
        >>> sanitize_filename("../etc/passwd")
        'etc_passwd'
        >>> sanitize_filename("my-spec-name")
        'my-spec-name'
        >>> sanitize_filename("spec@#$%name")
        'spec_name'
    """
    # Replace path separators and special chars with underscores
    safe = re.sub(r'[^\w\-_.]', '_', filename)
    # Remove leading/trailing dots and underscores
    safe = safe.strip('._')
    # Collapse consecutive underscores
    safe = re.sub(r'_+', '_', safe)
    # Truncate to max_length
    if len(safe) > max_length:
        safe = safe[:max_length].rstrip('._')
    # Ensure non-empty result
    return safe if safe else 'unnamed'


def write_artifacts(
    spec_artifacts: list[Any],
    last_response: str,
    output_dir: str | Path = "./artifacts",
    force: bool = False,
    *,
    variables: dict[str, str] | None = None,
    execution_context: dict[str, Any] | None = None,
    spec_name: str | None = None,
    pattern_type: str | None = None,
) -> list[str]:
    """Write output artifacts from workflow execution.

    Renders each artifact template with execution context (last_response, etc.)
    and writes to the specified paths. Creates parent directories as needed.

    Args:
        spec_artifacts: List of artifact configs from spec.outputs.artifacts
        last_response: The agent's last response text (for {{ last_response }} template)
        output_dir: Directory to write artifacts to (default: ./artifacts)
        force: If True, overwrite existing files; if False, error on existing files
        variables: User-provided variables from --var flags (for template rendering)
        execution_context: Additional context (steps, tasks) for template rendering
        spec_name: Name of spec (for $TRACE metadata)
        pattern_type: Pattern type (for $TRACE metadata)

    Returns:
        List of written file paths (absolute)

    Raises:
        ArtifactError: If directory creation fails, files exist without force=True,
                      template rendering fails, or file write fails
    """
    output_dir = Path(output_dir)
    written_files = []

    # Create output directory if needed
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ArtifactError(f"Failed to create output directory {output_dir}: {e}") from e

    # Template variables for artifact rendering
    # Supports {{ last_response }}, {{ TRACE }}, user variables from --var, etc.
    template_vars = {
        "last_response": last_response,
    }

    # Add TRACE variable if trace collector is available
    collector = get_trace_collector()
    if collector:
        trace_data = collector.get_trace_data(spec_name=spec_name, pattern=pattern_type)
        # Convert trace data to pretty-printed JSON
        trace_json = json.dumps(trace_data, indent=2, ensure_ascii=False)
        template_vars["TRACE"] = trace_json
        logger.debug(
            "trace_artifact_available",
            trace_id=trace_data.get("trace_id"),
            span_count=trace_data.get("span_count"),
        )
    else:
        # No trace collector; TRACE will be empty
        template_vars["TRACE"] = ""
        logger.debug("trace_artifact_unavailable", reason="telemetry_not_configured")

    # Merge user-provided variables (e.g., topic from --var topic="value")
    if variables:
        template_vars.update(variables)

    # Merge execution context (steps, tasks, etc.)
    if execution_context:
        template_vars.update(execution_context)

    for artifact in spec_artifacts:
        # Resolve artifact path (render template if it contains variables)
        try:
            rendered_path = render_template(artifact.path, template_vars)
        except Exception as e:
            raise ArtifactError(f"Failed to render artifact path '{artifact.path}': {e}") from e

        # Sanitize each path component after rendering to prevent traversal
        # This protects against templates like {{ "../../etc/passwd" }}
        path_obj = Path(rendered_path)

        # Block absolute paths (security: prevent writing outside project)
        if path_obj.is_absolute():
            logger.warning(
                "artifact_path_blocked",
                violation_type="absolute_path",
                attempted_path=rendered_path,
                artifact_template=artifact.path,
            )
            raise ArtifactError(
                f"Absolute paths not allowed in artifacts: {rendered_path}. "
                "Use relative paths only."
            )

        # Check for path traversal attempts BEFORE sanitizing (to catch "..")
        if ".." in path_obj.parts:
            logger.warning(
                "artifact_path_blocked",
                violation_type="path_traversal_attempt",
                attempted_path=rendered_path,
                artifact_template=artifact.path,
            )
            raise ArtifactError(
                f"Path traversal not allowed in artifacts: {rendered_path}. "
                "Paths cannot contain '..' components."
            )

        # Sanitize each path component to prevent other attacks
        sanitized_parts = [sanitize_filename(part) for part in path_obj.parts]
        safe_path = Path(*sanitized_parts)

        # Construct final path relative to output_dir
        artifact_path = (output_dir / safe_path).resolve()

        # Validate resolved path stays within output_dir (final defense)
        try:
            artifact_path.relative_to(output_dir.resolve())
        except ValueError:
            logger.warning(
                "artifact_path_blocked",
                violation_type="path_escape",
                attempted_path=str(artifact_path),
                artifact_template=artifact.path,
                output_dir=str(output_dir),
            )
            raise ArtifactError(
                f"Artifact path escapes output directory: {artifact_path}. "
                f"Paths must stay within {output_dir}."
            )

        # Block symlinks (security: prevent following links outside output_dir)
        if artifact_path.exists() and artifact_path.is_symlink():
            logger.warning(
                "artifact_path_blocked",
                violation_type="symlink_detected",
                attempted_path=str(artifact_path),
            )
            raise ArtifactError(
                f"Artifact path is a symlink: {artifact_path}. "
                "Symlinks are not allowed for security reasons."
            )

        # Check if file exists
        if artifact_path.exists() and not force:
            raise ArtifactError(
                f"Artifact file already exists: {artifact_path}. Use --force to overwrite."
            )

        # Render artifact content from template
        try:
            content = render_template(artifact.from_, template_vars)
        except Exception as e:
            raise ArtifactError(
                f"Failed to render artifact content for {artifact.path}: {e}"
            ) from e

        # Write the file
        try:
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(content, encoding="utf-8")
            written_files.append(str(artifact_path))
        except Exception as e:
            raise ArtifactError(f"Failed to write artifact to {artifact_path}: {e}") from e

    return written_files
