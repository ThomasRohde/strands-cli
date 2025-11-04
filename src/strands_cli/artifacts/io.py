"""Artifact output file management.

Handles writing workflow execution outputs to files using template rendering.
Supports Jinja2 templates for dynamic artifact content generation.

Features:
    - Template rendering with {{ last_response }} and future variables
    - Directory creation (parents created automatically)
    - Overwrite protection (--force flag required)
    - Error handling for I/O failures
    - UTF-8 encoding

Artifact Templates:
    Current: {{ last_response }} - final agent output
    Future: {{ TRACE }}, {{ PROVENANCE }}, etc.
"""

from pathlib import Path
from typing import Any

from strands_cli.loader import render_template


class ArtifactError(Exception):
    """Raised when artifact writing fails."""

    pass


def write_artifacts(
    spec_artifacts: list[Any],
    last_response: str,
    output_dir: str | Path = "./artifacts",
    force: bool = False,
    *,
    variables: dict[str, str] | None = None,
    execution_context: dict[str, Any] | None = None,
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
    # Supports {{ last_response }}, user variables from --var, and future OTEL metadata
    template_vars = {
        "last_response": last_response,
        # Future: Add $TRACE, $PROVENANCE, etc.
    }

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

        artifact_path = Path(rendered_path)

        # Make relative paths relative to output_dir
        if not artifact_path.is_absolute():
            artifact_path = output_dir / artifact_path

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
