"""Unit tests for file_read native tool.

Tests the file_read tool which reads file contents from the filesystem.
"""

import tempfile
from pathlib import Path


class TestFileReadToolSpec:
    """Test TOOL_SPEC definition for file_read."""

    def test_tool_spec_exists(self) -> None:
        """Test that TOOL_SPEC is defined in file_read module."""
        from strands_cli.tools import file_read

        assert hasattr(file_read, "TOOL_SPEC")
        assert isinstance(file_read.TOOL_SPEC, dict)

    def test_tool_spec_has_required_fields(self) -> None:
        """Test that TOOL_SPEC contains required Strands SDK fields."""
        from strands_cli.tools.file_read import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "file_read"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC

    def test_tool_spec_input_schema(self) -> None:
        """Test that TOOL_SPEC defines proper input schema."""
        from strands_cli.tools.file_read import TOOL_SPEC

        input_schema = TOOL_SPEC["inputSchema"]["json"]
        assert input_schema["type"] == "object"
        assert "path" in input_schema["properties"]
        assert "encoding" in input_schema["properties"]
        assert "path" in input_schema["required"]


class TestFileReadFunction:
    """Test file_read function behavior."""

    def test_file_read_callable_exists(self) -> None:
        """Test that file_read function is defined and callable."""
        from strands_cli.tools.file_read import file_read

        assert callable(file_read)

    def test_read_text_file_success(self) -> None:
        """Test reading a simple text file."""
        from strands_cli.tools.file_read import file_read

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Hello, World!\nThis is a test file.")
            temp_path = f.name

        try:
            tool_input = {"toolUseId": "test-123", "input": {"path": temp_path}}

            result = file_read(tool_input)

            assert result["toolUseId"] == "test-123"
            assert result["status"] == "success"
            assert len(result["content"]) == 1
            assert "Hello, World!" in result["content"][0]["text"]
            assert "This is a test file." in result["content"][0]["text"]
        finally:
            Path(temp_path).unlink()

    def test_read_multiline_file(self) -> None:
        """Test reading a file with multiple lines."""
        from strands_cli.tools.file_read import file_read

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Line 1\nLine 2\nLine 3\n")
            temp_path = f.name

        try:
            tool_input = {"toolUseId": "multiline", "input": {"path": temp_path}}

            result = file_read(tool_input)

            assert result["status"] == "success"
            content = result["content"][0]["text"]
            assert "Line 1" in content
            assert "Line 2" in content
            assert "Line 3" in content
        finally:
            Path(temp_path).unlink()

    def test_read_empty_file(self) -> None:
        """Test reading an empty file returns success with empty content."""
        from strands_cli.tools.file_read import file_read

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            tool_input = {"toolUseId": "empty", "input": {"path": temp_path}}

            result = file_read(tool_input)

            assert result["status"] == "success"
            assert result["content"][0]["text"] == ""
        finally:
            Path(temp_path).unlink()

    def test_missing_path_returns_error(self) -> None:
        """Test that missing path parameter returns error."""
        from strands_cli.tools.file_read import file_read

        tool_input = {"toolUseId": "no-path", "input": {}}

        result = file_read(tool_input)

        assert result["toolUseId"] == "no-path"
        assert result["status"] == "error"
        assert "required" in result["content"][0]["text"].lower()

    def test_empty_path_returns_error(self) -> None:
        """Test that empty path string returns error."""
        from strands_cli.tools.file_read import file_read

        tool_input = {"toolUseId": "empty-path", "input": {"path": ""}}

        result = file_read(tool_input)

        assert result["status"] == "error"
        assert "required" in result["content"][0]["text"].lower()

    def test_nonexistent_file_returns_error(self) -> None:
        """Test that reading nonexistent file returns error."""
        from strands_cli.tools.file_read import file_read

        tool_input = {
            "toolUseId": "not-found",
            "input": {"path": "/nonexistent/path/to/file.txt"},
        }

        result = file_read(tool_input)

        assert result["status"] == "error"
        assert "not found" in result["content"][0]["text"].lower()

    def test_directory_path_returns_error(self) -> None:
        """Test that providing a directory path returns error."""
        from strands_cli.tools.file_read import file_read

        with tempfile.TemporaryDirectory() as temp_dir:
            tool_input = {"toolUseId": "is-dir", "input": {"path": temp_dir}}

            result = file_read(tool_input)

            assert result["status"] == "error"
            assert "not a file" in result["content"][0]["text"].lower()

    def test_custom_encoding(self) -> None:
        """Test reading file with custom encoding."""
        from strands_cli.tools.file_read import file_read

        with tempfile.NamedTemporaryFile(mode="w", encoding="latin-1", delete=False) as f:
            f.write("Café résumé")
            temp_path = f.name

        try:
            tool_input = {
                "toolUseId": "encoding",
                "input": {"path": temp_path, "encoding": "latin-1"},
            }

            result = file_read(tool_input)

            assert result["status"] == "success"
            assert "Café résumé" in result["content"][0]["text"]
        finally:
            Path(temp_path).unlink()

    def test_relative_path_resolution(self) -> None:
        """Test that relative paths are resolved correctly."""
        from strands_cli.tools.file_read import file_read

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Relative path test")
            temp_path = f.name

        try:
            path = Path(temp_path)
            relative = path.name

            tool_input = {"toolUseId": "relative", "input": {"path": str(relative)}}

            file_read(tool_input)

        finally:
            Path(temp_path).unlink()

    def test_expanduser_tilde_path(self) -> None:
        """Test that tilde (~) in paths is expanded."""
        from strands_cli.tools.file_read import file_read

        home = Path.home()
        test_file = home / ".strands_test_file_read.txt"
        test_file.write_text("Tilde expansion test")

        try:
            tool_input = {"toolUseId": "tilde", "input": {"path": "~/.strands_test_file_read.txt"}}

            result = file_read(tool_input)

            assert result["status"] == "success"
            assert "Tilde expansion test" in result["content"][0]["text"]
        finally:
            test_file.unlink()


class TestFileReadToolIntegration:
    """Test file_read tool integration with registry."""

    def test_tool_registered_in_registry(self) -> None:
        """Test that file_read is auto-discovered by registry."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        tool_info = registry.get("file_read")

        assert tool_info is not None
        assert tool_info.id == "file_read"
        assert tool_info.module_path == "strands_cli.tools.file_read"

    def test_tool_in_registry_allowlist(self) -> None:
        """Test that file_read paths are in registry allowlist."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        allowlist = registry.get_allowlist()

        assert "file_read" in allowlist
        assert "strands_cli.tools.file_read" in allowlist

    def test_registry_resolves_short_id(self) -> None:
        """Test that registry resolves short ID to full path."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        resolved = registry.resolve("file_read")

        assert resolved == "strands_cli.tools.file_read"

    def test_load_python_callable_with_short_id(self) -> None:
        """Test that load_python_callable can load file_read with short ID."""
        from strands_cli.runtime.tools import load_python_callable

        tool_module = load_python_callable("file_read")

        assert hasattr(tool_module, "TOOL_SPEC")
        assert hasattr(tool_module, "file_read")
        assert callable(tool_module.file_read)
