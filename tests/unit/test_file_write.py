"""Unit tests for file_write native tool.

Tests the file_write tool which writes content to files on the filesystem.
"""

import tempfile
from pathlib import Path


class TestFileWriteToolSpec:
    """Test TOOL_SPEC definition for file_write."""

    def test_tool_spec_exists(self) -> None:
        """Test that TOOL_SPEC is defined in file_write module."""
        from strands_cli.tools import file_write

        assert hasattr(file_write, "TOOL_SPEC")
        assert isinstance(file_write.TOOL_SPEC, dict)

    def test_tool_spec_has_required_fields(self) -> None:
        """Test that TOOL_SPEC contains required Strands SDK fields."""
        from strands_cli.tools.file_write import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "file_write"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC

    def test_tool_spec_input_schema(self) -> None:
        """Test that TOOL_SPEC defines proper input schema."""
        from strands_cli.tools.file_write import TOOL_SPEC

        input_schema = TOOL_SPEC["inputSchema"]["json"]
        assert input_schema["type"] == "object"
        assert "path" in input_schema["properties"]
        assert "content" in input_schema["properties"]
        assert "encoding" in input_schema["properties"]
        assert "create_dirs" in input_schema["properties"]
        assert "path" in input_schema["required"]
        assert "content" in input_schema["required"]


class TestFileWriteFunction:
    """Test file_write function behavior."""

    def test_file_write_callable_exists(self) -> None:
        """Test that file_write function is defined and callable."""
        from strands_cli.tools.file_write import file_write

        assert callable(file_write)

    def test_write_text_file_success(self) -> None:
        """Test writing a simple text file."""
        from strands_cli.tools.file_write import file_write

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test.txt"

            tool_input = {
                "toolUseId": "test-123",
                "input": {"path": str(temp_path), "content": "Hello, World!\nTest content."},
            }

            result = file_write(tool_input)

            assert result["toolUseId"] == "test-123"
            assert result["status"] == "success"
            assert "Successfully wrote" in result["content"][0]["text"]

            written_content = temp_path.read_text()
            assert written_content == "Hello, World!\nTest content."

    def test_write_multiline_content(self) -> None:
        """Test writing multiline content."""
        from strands_cli.tools.file_write import file_write

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "multiline.txt"

            content = "Line 1\nLine 2\nLine 3\n"
            tool_input = {"toolUseId": "multiline", "input": {"path": str(temp_path), "content": content}}

            result = file_write(tool_input)

            assert result["status"] == "success"
            assert temp_path.read_text() == content

    def test_write_empty_content(self) -> None:
        """Test writing empty content creates empty file."""
        from strands_cli.tools.file_write import file_write

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "empty.txt"

            tool_input = {"toolUseId": "empty", "input": {"path": str(temp_path), "content": ""}}

            result = file_write(tool_input)

            assert result["status"] == "success"
            assert temp_path.read_text() == ""

    def test_overwrite_existing_file(self) -> None:
        """Test that writing to existing file overwrites it."""
        from strands_cli.tools.file_write import file_write

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "overwrite.txt"
            temp_path.write_text("Old content")

            tool_input = {
                "toolUseId": "overwrite",
                "input": {"path": str(temp_path), "content": "New content"},
            }

            result = file_write(tool_input)

            assert result["status"] == "success"
            assert temp_path.read_text() == "New content"

    def test_missing_path_returns_error(self) -> None:
        """Test that missing path parameter returns error."""
        from strands_cli.tools.file_write import file_write

        tool_input = {"toolUseId": "no-path", "input": {"content": "test"}}

        result = file_write(tool_input)

        assert result["toolUseId"] == "no-path"
        assert result["status"] == "error"
        assert "required" in result["content"][0]["text"].lower()

    def test_empty_path_returns_error(self) -> None:
        """Test that empty path string returns error."""
        from strands_cli.tools.file_write import file_write

        tool_input = {"toolUseId": "empty-path", "input": {"path": "", "content": "test"}}

        result = file_write(tool_input)

        assert result["status"] == "error"
        assert "required" in result["content"][0]["text"].lower()

    def test_missing_content_returns_error(self) -> None:
        """Test that missing content parameter returns error."""
        from strands_cli.tools.file_write import file_write

        tool_input = {"toolUseId": "no-content", "input": {"path": "/tmp/test.txt"}}

        result = file_write(tool_input)

        assert result["status"] == "error"
        assert "required" in result["content"][0]["text"].lower()

    def test_directory_path_returns_error(self) -> None:
        """Test that providing a directory path returns error."""
        from strands_cli.tools.file_write import file_write

        with tempfile.TemporaryDirectory() as temp_dir:
            tool_input = {"toolUseId": "is-dir", "input": {"path": temp_dir, "content": "test"}}

            result = file_write(tool_input)

            assert result["status"] == "error"
            assert "directory" in result["content"][0]["text"].lower()

    def test_nonexistent_parent_without_create_dirs_returns_error(self) -> None:
        """Test that nonexistent parent directory returns error when create_dirs is false."""
        from strands_cli.tools.file_write import file_write

        nonexistent_path = "/nonexistent/path/to/file.txt"
        tool_input = {
            "toolUseId": "no-parent",
            "input": {"path": nonexistent_path, "content": "test"},
        }

        result = file_write(tool_input)

        assert result["status"] == "error"
        assert "directory does not exist" in result["content"][0]["text"].lower()

    def test_create_dirs_creates_parent_directories(self) -> None:
        """Test that create_dirs option creates parent directories."""
        from strands_cli.tools.file_write import file_write

        with tempfile.TemporaryDirectory() as temp_dir:
            nested_path = Path(temp_dir) / "sub1" / "sub2" / "file.txt"

            tool_input = {
                "toolUseId": "create-dirs",
                "input": {"path": str(nested_path), "content": "test", "create_dirs": True},
            }

            result = file_write(tool_input)

            assert result["status"] == "success"
            assert nested_path.exists()
            assert nested_path.read_text() == "test"

    def test_custom_encoding(self) -> None:
        """Test writing file with custom encoding."""
        from strands_cli.tools.file_write import file_write

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "encoded.txt"

            tool_input = {
                "toolUseId": "encoding",
                "input": {"path": str(temp_path), "content": "Café résumé", "encoding": "latin-1"},
            }

            result = file_write(tool_input)

            assert result["status"] == "success"
            assert temp_path.read_text(encoding="latin-1") == "Café résumé"

    def test_expanduser_tilde_path(self) -> None:
        """Test that tilde (~) in paths is expanded."""
        from strands_cli.tools.file_write import file_write

        home = Path.home()
        test_file = home / ".strands_test_file_write.txt"

        try:
            tool_input = {
                "toolUseId": "tilde",
                "input": {"path": "~/.strands_test_file_write.txt", "content": "Tilde test"},
            }

            result = file_write(tool_input)

            assert result["status"] == "success"
            assert test_file.exists()
            assert test_file.read_text() == "Tilde test"
        finally:
            if test_file.exists():
                test_file.unlink()


class TestFileWriteToolIntegration:
    """Test file_write tool integration with registry."""

    def test_tool_registered_in_registry(self) -> None:
        """Test that file_write is auto-discovered by registry."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        tool_info = registry.get("file_write")

        assert tool_info is not None
        assert tool_info.id == "file_write"
        assert tool_info.module_path == "strands_cli.tools.file_write"

    def test_tool_in_registry_allowlist(self) -> None:
        """Test that file_write paths are in registry allowlist."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        allowlist = registry.get_allowlist()

        assert "file_write" in allowlist
        assert "strands_cli.tools.file_write" in allowlist

    def test_registry_resolves_short_id(self) -> None:
        """Test that registry resolves short ID to full path."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        resolved = registry.resolve("file_write")

        assert resolved == "strands_cli.tools.file_write"

    def test_load_python_callable_with_short_id(self) -> None:
        """Test that load_python_callable can load file_write with short ID."""
        from strands_cli.runtime.tools import load_python_callable

        tool_module = load_python_callable("file_write")

        assert hasattr(tool_module, "TOOL_SPEC")
        assert hasattr(tool_module, "file_write")
        assert callable(tool_module.file_write)
