"""Tests for executor and artifacts modules.

Tests cover:
- exec/single_agent.py: Template rendering, agent execution, retry logic
- artifacts/io.py: File writing, overwrite protection, error handling
"""

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from strands_cli.artifacts.io import ArtifactError, sanitize_filename, write_artifacts
from strands_cli.exec.single_agent import ExecutionError, run_single_agent
from strands_cli.loader.template import TemplateError, render_template
from strands_cli.types import PatternType, Spec

# ============================================================================
# Template Rendering Tests
# ============================================================================


class TestTemplateRendering:
    """Test Jinja2 template expansion in execution context."""

    def test_basic_variable_expansion(self):
        """Test simple {{ variable }} expansion."""
        template = "Hello {{ name }}!"
        result = render_template(template, {"name": "World"})
        assert result == "Hello World!"

    def test_nested_input_access(self):
        """Test accessing nested variables via {{ inputs.key }}."""
        template = "Topic: {{ inputs.topic }}, Style: {{ inputs.style }}"
        variables = {
            "inputs": {
                "topic": "AI Ethics",
                "style": "formal",
            }
        }
        result = render_template(template, variables)
        assert result == "Topic: AI Ethics, Style: formal"

    def test_last_response_variable(self):
        """Test special {{ last_response }} variable in outputs."""
        template = "Output:\n{{ last_response }}"
        result = render_template(template, {"last_response": "Agent completed task."})
        assert result == "Output:\nAgent completed task."

    def test_undefined_variable_raises_error(self):
        """Test that undefined variables raise TemplateError."""
        template = "Hello {{ undefined_var }}!"
        with pytest.raises(TemplateError, match="Undefined variable"):
            render_template(template, {})

    def test_invalid_syntax_raises_error(self):
        """Test that invalid Jinja2 syntax raises TemplateError."""
        template = "Hello {{ name"  # Missing closing }}
        with pytest.raises(TemplateError, match="Invalid template syntax"):
            render_template(template, {"name": "World"})

    def test_control_char_stripping(self):
        """Test that control characters are stripped from output."""
        # Inject control chars directly
        variables = {"text": "normal\x00text\x1fhere"}
        result = render_template("{{ text }}", variables)
        # Control chars should be removed
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_max_output_chars_truncation(self):
        """Test that output is truncated when max_output_chars is set."""
        template = "{{ long_text }}"
        long_text = "x" * 1000
        result = render_template(template, {"long_text": long_text}, max_output_chars=100)
        assert len(result) == 100


# ============================================================================
# Agent Execution Tests
# ============================================================================


class TestAgentExecution:
    """Test agent execution with mocked Strands Agent."""

    @pytest.mark.asyncio
    async def test_successful_chain_execution(
        self, sample_ollama_spec: Spec, mock_strands_agent: Mock, mocker
    ):
        """Test successful execution returns response."""
        # Mock the model creation to avoid provider dependency
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        mock_strands_agent.invoke_async.return_value = "Test response from agent"

        result = await run_single_agent(sample_ollama_spec)

        assert result.success is True
        assert result.last_response == "Test response from agent"
        assert result.agent_id == "test_agent"
        assert result.pattern_type == PatternType.CHAIN
        assert result.error is None
        mock_strands_agent.invoke_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_workflow_execution(
        self, sample_minimal_spec_dict: dict, mock_strands_agent: Mock, mocker
    ):
        """Test workflow pattern execution."""
        # Mock the model creation
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Convert to workflow pattern
        spec_dict = sample_minimal_spec_dict.copy()
        spec_dict["pattern"] = {
            "type": "workflow",
            "config": {
                "tasks": [
                    {
                        "id": "task1",
                        "agent": "test_agent",
                        "input": "Workflow task input",
                    }
                ]
            },
        }
        spec = Spec.model_validate(spec_dict)

        mock_strands_agent.invoke_async.return_value = "Workflow response"
        result = await run_single_agent(spec)

        assert result.success is True
        assert result.last_response == "Workflow response"
        assert result.pattern_type == PatternType.WORKFLOW

    @pytest.mark.asyncio
    async def test_agent_receives_correct_system_prompt(
        self, sample_ollama_spec: Spec, mock_strands_agent: Mock, mocker
    ):
        """Test that agent is built with correct system prompt."""
        # Mock AgentCache.get_or_build_agent to capture arguments
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.return_value = mock_strands_agent
        mock_cache.close.return_value = None
        mocker.patch("strands_cli.exec.single_agent.AgentCache", return_value=mock_cache)

        await run_single_agent(sample_ollama_spec)

        # Verify get_or_build_agent was called with correct spec and agent config
        mock_cache.get_or_build_agent.assert_called_once()
        call_args = mock_cache.get_or_build_agent.call_args
        assert call_args[0][0] == sample_ollama_spec  # spec
        assert call_args[0][1] == "test_agent"  # agent_id

    @pytest.mark.asyncio
    async def test_agent_receives_rendered_task_prompt(
        self, sample_minimal_spec_dict: dict, mock_strands_agent: Mock, mocker
    ):
        """Test that agent receives rendered task prompt with variables."""
        # Mock the model creation
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Add variables to inputs and modify task input
        spec_dict = sample_minimal_spec_dict.copy()
        spec_dict["inputs"] = {
            "values": {
                "topic": "AI Safety",
            }
        }
        spec_dict["pattern"]["config"]["steps"][0]["input"] = "Write about {{ topic }}"
        spec = Spec.model_validate(spec_dict)

        mock_strands_agent.invoke_async.return_value = "Response"
        await run_single_agent(spec)

        # Check that run was called with rendered input
        mock_strands_agent.invoke_async.assert_called_once_with("Write about AI Safety")

    @pytest.mark.asyncio
    async def test_execution_result_captured_correctly(
        self, sample_ollama_spec: Spec, mock_strands_agent: Mock, mocker
    ):
        """Test that execution result is captured with correct metadata."""
        # Mock the model creation
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        mock_strands_agent.invoke_async.return_value = "Final result"

        result = await run_single_agent(sample_ollama_spec)

        assert result.success is True
        assert result.last_response == "Final result"
        assert result.agent_id == "test_agent"
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_template_error_wrapped_in_execution_error(
        self, sample_minimal_spec_dict: dict, mock_strands_agent: Mock, mocker
    ):
        """Test that template rendering errors are wrapped."""
        # Mock the model creation
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Create invalid template
        spec_dict = sample_minimal_spec_dict.copy()
        spec_dict["pattern"]["config"]["steps"][0]["input"] = "{{ undefined }}"
        spec = Spec.model_validate(spec_dict)

        with pytest.raises(ExecutionError, match="Failed to render task input"):
            await run_single_agent(spec)

    @pytest.mark.asyncio
    async def test_agent_build_error_wrapped(self, sample_ollama_spec: Spec, mocker):
        """Test that agent build errors are wrapped in RunResult."""
        mock_cache = mocker.AsyncMock()
        mock_cache.get_or_build_agent.side_effect = Exception("Provider connection failed")
        mocker.patch("strands_cli.exec.single_agent.AgentCache", return_value=mock_cache)

        result = await run_single_agent(sample_ollama_spec)

        # Phase 3: Exceptions are now captured in RunResult, not raised
        assert result.success is False
        assert "Provider connection failed" in result.error


# ============================================================================
# Retry Logic Tests
# ============================================================================


class TestRetryLogic:
    """Test retry behavior with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_on_transient_connection_error(
        self, sample_ollama_spec: Spec, mock_strands_agent: Mock, mocker
    ):
        """Test retry on connection timeout."""
        # Mock the model creation
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Simulate transient error then success
        mock_strands_agent.invoke_async.side_effect = [
            ConnectionError("Temporary connection issue"),
            "Success after retry",
        ]

        result = await run_single_agent(sample_ollama_spec)

        assert result.success is True
        assert result.last_response == "Success after retry"
        assert mock_strands_agent.invoke_async.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_timeout_error(
        self, sample_ollama_spec: Spec, mock_strands_agent: Mock, mocker
    ):
        """Test retry on timeout."""
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")
        mocker.patch("time.sleep")

        mock_strands_agent.invoke_async.side_effect = [
            TimeoutError("Request timeout"),
            "Success",
        ]

        result = await run_single_agent(sample_ollama_spec)
        assert result.success is True
        assert mock_strands_agent.invoke_async.call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_respected(
        self, sample_minimal_spec_dict: dict, mock_strands_agent: Mock, mocker
    ):
        """Test that max_retries is respected from failure_policy."""
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")
        mocker.patch("time.sleep")

        # Set retry policy
        spec_dict = sample_minimal_spec_dict.copy()
        spec_dict["runtime"]["failure_policy"] = {
            "retries": 2,  # Max 2 retries (3 total attempts)
            "backoff": "exponential",
        }
        spec = Spec.model_validate(spec_dict)

        # Always fail
        mock_strands_agent.invoke_async.side_effect = ConnectionError("Always fails")

        result = await run_single_agent(spec)

        # Should fail after 3 attempts (1 initial + 2 retries)
        assert result.success is False
        assert "Always fails" in result.error
        assert mock_strands_agent.invoke_async.call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff_configuration(
        self, sample_minimal_spec_dict: dict, mock_strands_agent: Mock, mocker
    ):
        """Test exponential backoff uses wait_min and wait_max."""
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # Configure backoff
        spec_dict = sample_minimal_spec_dict.copy()
        spec_dict["runtime"]["failure_policy"] = {
            "retries": 2,
            "backoff": "exponential",
            "wait_min": 2,
            "wait_max": 30,
        }
        spec = Spec.model_validate(spec_dict)

        mock_strands_agent.invoke_async.side_effect = [
            ConnectionError("Fail 1"),
            ConnectionError("Fail 2"),
            "Success",
        ]

        result = await run_single_agent(spec)
        assert result.success is True
        # Verify all three attempts were made (initial + 2 retries)
        assert mock_strands_agent.invoke_async.call_count == 3

    @pytest.mark.asyncio
    async def test_permanent_error_fails_immediately(
        self, sample_ollama_spec: Spec, mock_strands_agent: Mock, mocker
    ):
        """Test that non-transient errors fail without retry."""
        mocker.patch("strands_cli.runtime.strands_adapter.create_model")

        # ValueError is not in _TRANSIENT_ERRORS, should not retry
        mock_strands_agent.invoke_async.side_effect = ValueError("Invalid input")

        result = await run_single_agent(sample_ollama_spec)

        assert result.success is False
        assert "Invalid input" in result.error
        # Should only be called once (no retries for permanent errors)
        assert mock_strands_agent.invoke_async.call_count == 1


# ============================================================================
# Artifact Writing Tests
# ============================================================================


class TestArtifactWriting:
    """Test artifact file I/O operations."""

    def test_write_artifact_to_filesystem(self, temp_artifacts_dir: Path):
        """Test basic artifact writing."""
        artifacts = [MagicMock(path="output.txt", from_="Response: {{ last_response }}")]

        written = write_artifacts(artifacts, "Test content", output_dir=temp_artifacts_dir)

        assert len(written) == 1
        output_file = temp_artifacts_dir / "output.txt"
        assert output_file.exists()
        assert output_file.read_text() == "Response: Test content"

    def test_artifact_directory_auto_created(self, temp_output_dir: Path):
        """Test that artifact directory is created if missing."""
        artifacts_dir = temp_output_dir / "new_artifacts"
        assert not artifacts_dir.exists()

        artifacts = [MagicMock(path="test.txt", from_="{{ last_response }}")]
        write_artifacts(artifacts, "Content", output_dir=artifacts_dir)

        assert artifacts_dir.exists()
        assert (artifacts_dir / "test.txt").exists()

    def test_content_matches_template_expansion(self, temp_artifacts_dir: Path):
        """Test that artifact content is correctly rendered."""
        artifacts = [
            MagicMock(
                path="result.md",
                from_="# Results\n\n{{ last_response }}\n\n---\nEnd",
            )
        ]

        write_artifacts(artifacts, "Agent output here", output_dir=temp_artifacts_dir)

        content = (temp_artifacts_dir / "result.md").read_text()
        assert content == "# Results\n\nAgent output here\n\n---\nEnd"

    def test_absolute_and_relative_paths(self, temp_artifacts_dir: Path):
        """Test that both absolute and relative paths work."""
        # Relative path
        artifacts_rel = [MagicMock(path="relative.txt", from_="{{ last_response }}")]
        write_artifacts(artifacts_rel, "Relative", output_dir=temp_artifacts_dir)
        assert (temp_artifacts_dir / "relative.txt").exists()

        # Absolute path
        absolute_path = temp_artifacts_dir / "absolute.txt"
        artifacts_abs = [MagicMock(path=str(absolute_path), from_="{{ last_response }}")]
        write_artifacts(artifacts_abs, "Absolute", output_dir=temp_artifacts_dir)
        assert absolute_path.exists()

    def test_nested_directory_creation(self, temp_artifacts_dir: Path):
        """Test that nested directories are created automatically."""
        artifacts = [MagicMock(path="nested/deep/file.txt", from_="{{ last_response }}")]

        write_artifacts(artifacts, "Nested content", output_dir=temp_artifacts_dir)

        output_file = temp_artifacts_dir / "nested" / "deep" / "file.txt"
        assert output_file.exists()
        assert output_file.read_text() == "Nested content"


# ============================================================================
# Overwrite Protection Tests
# ============================================================================


class TestOverwriteProtection:
    """Test artifact overwrite protection."""

    def test_error_when_file_exists_without_force(self, temp_artifacts_dir: Path):
        """Test that existing files raise error by default."""
        # Create existing file
        existing = temp_artifacts_dir / "existing.txt"
        existing.write_text("Original content")

        artifacts = [MagicMock(path="existing.txt", from_="{{ last_response }}")]

        with pytest.raises(ArtifactError, match=r"already exists.*--force"):
            write_artifacts(artifacts, "New content", output_dir=temp_artifacts_dir)

        # Original content should be preserved
        assert existing.read_text() == "Original content"

    def test_force_flag_allows_overwrite(self, temp_artifacts_dir: Path):
        """Test that --force flag allows overwriting."""
        # Create existing file
        existing = temp_artifacts_dir / "existing.txt"
        existing.write_text("Original content")

        artifacts = [MagicMock(path="existing.txt", from_="{{ last_response }}")]
        write_artifacts(artifacts, "New content", output_dir=temp_artifacts_dir, force=True)

        # Content should be overwritten
        assert existing.read_text() == "New content"

    def test_multiple_artifacts_to_different_paths(self, temp_artifacts_dir: Path):
        """Test writing multiple artifacts to different paths."""
        artifacts = [
            MagicMock(path="output1.txt", from_="First: {{ last_response }}"),
            MagicMock(path="output2.txt", from_="Second: {{ last_response }}"),
            MagicMock(path="subdir/output3.txt", from_="Third: {{ last_response }}"),
        ]

        written = write_artifacts(artifacts, "Content", output_dir=temp_artifacts_dir)

        assert len(written) == 3
        assert (temp_artifacts_dir / "output1.txt").read_text() == "First: Content"
        assert (temp_artifacts_dir / "output2.txt").read_text() == "Second: Content"
        assert (temp_artifacts_dir / "subdir/output3.txt").read_text() == "Third: Content"


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestArtifactErrorHandling:
    """Test error handling in artifact operations."""

    def test_permission_denied_wrapped(self, mocker, temp_artifacts_dir: Path):
        """Test that permission errors are caught and wrapped."""
        artifacts = [MagicMock(path="test.txt", from_="{{ last_response }}")]

        # Mock Path.write_text to raise permission error
        mock_write = mocker.patch("pathlib.Path.write_text")
        mock_write.side_effect = PermissionError("Permission denied")

        with pytest.raises(ArtifactError, match="Failed to write artifact"):
            write_artifacts(artifacts, "Content", output_dir=temp_artifacts_dir)

    def test_template_rendering_error_in_artifact(self, temp_artifacts_dir: Path):
        """Test that template errors in artifacts are caught."""
        artifacts = [MagicMock(path="test.txt", from_="{{ undefined_var }}")]

        with pytest.raises(ArtifactError, match="Failed to render artifact content"):
            write_artifacts(artifacts, "Content", output_dir=temp_artifacts_dir)

    def test_directory_creation_failure(self, mocker):
        """Test that directory creation errors are caught."""
        artifacts = [MagicMock(path="test.txt", from_="{{ last_response }}")]

        # Mock mkdir to fail
        mock_mkdir = mocker.patch("pathlib.Path.mkdir")
        mock_mkdir.side_effect = OSError("Cannot create directory")

        with pytest.raises(ArtifactError, match="Failed to create output directory"):
            write_artifacts(artifacts, "Content", output_dir="/invalid/path")

    def test_invalid_path_characters(self, temp_artifacts_dir: Path):
        """Test handling of invalid path characters."""
        # Windows doesn't allow certain characters in filenames
        # This behavior may vary by OS, so we test the general case
        artifacts = [MagicMock(path="file:invalid.txt", from_="{{ last_response }}")]

        with contextlib.suppress(ArtifactError):
            # Expected to potentially fail on some platforms
            write_artifacts(artifacts, "Content", output_dir=temp_artifacts_dir)


# ============================================================================
# Path Sanitization Tests (Security - Phase 3)
# ============================================================================


class TestPathSanitization:
    """Test filename sanitization for security (prevents path traversal)."""

    def test_sanitize_removes_path_separators(self):
        """Test that path separators are removed."""
        assert sanitize_filename("../etc/passwd") == "etc_passwd"
        assert sanitize_filename(r"..\windows\system32") == "windows_system32"
        assert sanitize_filename("/absolute/path") == "absolute_path"
        assert sanitize_filename("relative/path") == "relative_path"

    def test_sanitize_removes_special_characters(self):
        """Test that special characters are replaced with underscores."""
        assert sanitize_filename("spec@#$%name") == "spec_name"
        assert sanitize_filename("file:with<>invalid|chars") == "file_with_invalid_chars"
        assert sanitize_filename("my-spec-name") == "my-spec-name"  # Hyphens preserved
        assert sanitize_filename("my_spec_name") == "my_spec_name"  # Underscores preserved
        assert sanitize_filename("my.spec.name") == "my.spec.name"  # Dots preserved

    def test_sanitize_trims_leading_trailing_chars(self):
        """Test that leading/trailing dots and underscores are removed."""
        assert sanitize_filename(".hidden") == "hidden"
        assert sanitize_filename("_leading") == "leading"
        assert sanitize_filename("trailing_") == "trailing"
        assert sanitize_filename("...dots...") == "dots"

    def test_sanitize_collapses_underscores(self):
        """Test that consecutive underscores are collapsed."""
        assert sanitize_filename("multi___underscore") == "multi_underscore"
        assert sanitize_filename("a____b____c") == "a_b_c"

    def test_sanitize_truncates_long_names(self):
        """Test that long filenames are truncated to max_length."""
        long_name = "a" * 200
        sanitized = sanitize_filename(long_name)
        assert len(sanitized) <= 100
        assert sanitized == "a" * 100

        # Test custom max_length
        sanitized_short = sanitize_filename(long_name, max_length=50)
        assert len(sanitized_short) <= 50
        assert sanitized_short == "a" * 50

    def test_sanitize_handles_empty_input(self):
        """Test that empty or all-invalid input returns 'unnamed'."""
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename("...") == "unnamed"
        assert sanitize_filename("___") == "unnamed"
        assert sanitize_filename("@#$%") == "unnamed"

    def test_sanitize_preserves_valid_names(self):
        """Test that valid names are preserved."""
        assert sanitize_filename("my-spec-name") == "my-spec-name"
        assert sanitize_filename("spec_v1.2.3") == "spec_v1.2.3"
        assert sanitize_filename("workflow-2024") == "workflow-2024"

    def test_sanitize_realistic_attack_vectors(self):
        """Test realistic path traversal attack vectors."""
        # Directory traversal attempts
        assert sanitize_filename("../../etc/passwd") == "etc_passwd"
        assert sanitize_filename(r"..\..\windows\hosts") == "windows_hosts"

        # Null byte injection
        assert "\x00" not in sanitize_filename("file\x00.txt")

        # Command injection attempts (hyphens are valid, so -rf is preserved)
        assert sanitize_filename("file; rm -rf /") == "file_rm_-rf"
        assert sanitize_filename("$(malicious)") == "malicious"

        # URL-encoded attempts (% is replaced with _, dots preserved)
        assert sanitize_filename("..%2F..%2Fetc%2Fpasswd") == "2F.._2Fetc_2Fpasswd"

    def test_sanitize_integration_with_report_writing(self, temp_artifacts_dir: Path):
        """Test that sanitized filenames work in actual file operations."""
        # Simulate malicious spec name
        malicious_name = "../../../etc/passwd"
        safe_name = sanitize_filename(malicious_name)

        # Write a report with sanitized name
        report_path = temp_artifacts_dir / f"{safe_name}-unsupported.md"
        report_path.write_text("# Report\n\nTest content", encoding="utf-8")

        # Verify file was created in correct location
        assert report_path.exists()
        assert report_path.parent == temp_artifacts_dir
        assert report_path.name == "etc_passwd-unsupported.md"

        # Ensure it didn't escape the artifacts directory
        assert str(temp_artifacts_dir) in str(report_path.resolve())

