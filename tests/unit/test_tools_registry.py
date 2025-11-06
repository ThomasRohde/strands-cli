"""Tests for the native tools registry."""

from types import ModuleType
from unittest.mock import Mock

from strands_cli.tools.registry import ToolInfo, ToolRegistry, get_registry


class TestToolInfo:
    """Tests for ToolInfo dataclass."""

    def test_tool_info_creation(self):
        """Test ToolInfo can be created with required fields."""
        tool_info = ToolInfo(
            id="test_tool",
            module_path="strands_cli.tools.test_tool",
            description="A test tool",
        )

        assert tool_info.id == "test_tool"
        assert tool_info.module_path == "strands_cli.tools.test_tool"
        assert tool_info.description == "A test tool"

    def test_import_path_property(self):
        """Test import_path property returns module_path."""
        tool_info = ToolInfo(
            id="http_request",
            module_path="strands_cli.tools.http_request",
            description="HTTP request tool",
        )

        assert tool_info.import_path == "strands_cli.tools.http_request"

    def test_legacy_path_property(self):
        """Test legacy_path property returns strands_tools format."""
        tool_info = ToolInfo(
            id="http_request",
            module_path="strands_cli.tools.http_request",
            description="HTTP request tool",
        )

        assert tool_info.legacy_path == "strands_tools.http_request.http_request"

    def test_legacy_short_property(self):
        """Test legacy_short property returns short strands_tools format."""
        tool_info = ToolInfo(
            id="http_request",
            module_path="strands_cli.tools.http_request",
            description="HTTP request tool",
        )

        assert tool_info.legacy_short == "strands_tools.http_request"


class TestToolRegistrySingleton:
    """Tests for ToolRegistry singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Test that multiple ToolRegistry() calls return the same instance."""
        # Reset to clean state
        if ToolRegistry._instance:
            ToolRegistry._instance._reset()

        registry1 = ToolRegistry()
        registry2 = ToolRegistry()

        assert registry1 is registry2

    def test_get_registry_returns_singleton(self):
        """Test that get_registry() returns the singleton instance."""
        # Reset to clean state
        if ToolRegistry._instance:
            ToolRegistry._instance._reset()

        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2
        assert isinstance(registry1, ToolRegistry)


class TestToolRegistryDiscovery:
    """Tests for tool auto-discovery mechanism."""

    def test_discover_tools_with_mock_modules(self, mocker):
        """Test auto-discovery with mocked tool modules."""
        # Create mock module with valid TOOL_SPEC
        mock_module = Mock(spec=ModuleType)
        mock_module.TOOL_SPEC = {
            "name": "test_tool",
            "description": "A test tool for discovery",
        }

        # Mock pkgutil.iter_modules to return our mock module
        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[
                (None, "test_tool", False),  # (importer, module_name, is_pkg)
            ],
        )

        # Mock importlib.import_module to return our mock module
        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            return_value=mock_module,
        )

        # Create a fresh registry
        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        # Verify tool was discovered
        tools = registry.list_all()
        assert len(tools) == 1
        assert tools[0].id == "test_tool"
        assert tools[0].module_path == "strands_cli.tools.test_tool"
        assert tools[0].description == "A test tool for discovery"

    def test_discover_skips_modules_without_tool_spec(self, mocker, capsys):
        """Test that discovery skips modules without TOOL_SPEC and logs warning."""
        # Create mock module without TOOL_SPEC
        mock_module = Mock(spec=ModuleType)
        # Explicitly set hasattr to return False
        del mock_module.TOOL_SPEC

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[
                (None, "bad_tool", False),
            ],
        )

        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            return_value=mock_module,
        )

        # Create a fresh registry
        registry = ToolRegistry()
        registry._tools.clear()

        registry._discover_tools()

        # Verify tool was NOT discovered
        tools = registry.list_all()
        assert len(tools) == 0

        # Verify warning was logged to stdout (structlog behavior)
        captured = capsys.readouterr()
        assert "missing TOOL_SPEC" in captured.out

    def test_discover_skips_modules_with_invalid_tool_spec(self, mocker, capsys):
        """Test that discovery skips modules with invalid TOOL_SPEC."""
        # Create mock module with invalid TOOL_SPEC (missing 'name')
        mock_module = Mock(spec=ModuleType)
        mock_module.TOOL_SPEC = {"description": "Missing name field"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[
                (None, "invalid_tool", False),
            ],
        )

        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            return_value=mock_module,
        )

        registry = ToolRegistry()
        registry._tools.clear()

        registry._discover_tools()

        tools = registry.list_all()
        assert len(tools) == 0

        captured = capsys.readouterr()
        assert "invalid TOOL_SPEC" in captured.out

    def test_discover_handles_import_errors(self, mocker, capsys):
        """Test that discovery handles import errors gracefully."""
        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[
                (None, "broken_tool", False),
            ],
        )

        # Mock import to raise an exception
        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            side_effect=ImportError("Module not found"),
        )

        registry = ToolRegistry()
        registry._tools.clear()

        registry._discover_tools()

        tools = registry.list_all()
        assert len(tools) == 0

        captured = capsys.readouterr()
        assert "Failed to import" in captured.out

    def test_discover_logs_duplicate_tool_ids(self, mocker, capsys):
        """Test that discovery logs warning for duplicate tool IDs."""
        # Create two mock modules with same tool ID
        mock_module1 = Mock(spec=ModuleType)
        mock_module1.TOOL_SPEC = {"name": "duplicate_tool", "description": "First"}

        mock_module2 = Mock(spec=ModuleType)
        mock_module2.TOOL_SPEC = {"name": "duplicate_tool", "description": "Second"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[
                (None, "tool_one", False),
                (None, "tool_two", False),
            ],
        )

        import_mock = mocker.patch("strands_cli.tools.registry.importlib.import_module")
        import_mock.side_effect = [mock_module1, mock_module2]

        registry = ToolRegistry()
        registry._tools.clear()

        registry._discover_tools()

        # Should have one tool (last wins)
        tools = registry.list_all()
        assert len(tools) == 1
        assert tools[0].id == "duplicate_tool"

        # Verify warning was logged
        captured = capsys.readouterr()
        assert "Duplicate tool ID" in captured.out

    def test_discover_skips_special_modules(self, mocker):
        """Test that discovery skips __init__, registry, and other special files."""
        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[
                (None, "__init__", False),
                (None, "_private", False),
                (None, "registry", False),
            ],
        )

        import_mock = mocker.patch("strands_cli.tools.registry.importlib.import_module")

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        # No imports should have been attempted
        assert import_mock.call_count == 0


class TestToolRegistryMethods:
    """Tests for ToolRegistry public methods."""

    def test_get_returns_tool_by_id(self, mocker):
        """Test get() returns tool by ID."""
        mock_module = Mock(spec=ModuleType)
        mock_module.TOOL_SPEC = {"name": "test_tool", "description": "Test"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[(None, "test_tool", False)],
        )
        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            return_value=mock_module,
        )

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        tool = registry.get("test_tool")
        assert tool is not None
        assert tool.id == "test_tool"

    def test_get_returns_none_for_unknown_tool(self, mocker):
        """Test get() returns None for unknown tool ID."""
        mocker.patch("strands_cli.tools.registry.pkgutil.iter_modules", return_value=[])

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        tool = registry.get("unknown_tool")
        assert tool is None

    def test_list_all_returns_all_tools(self, mocker):
        """Test list_all() returns all discovered tools."""
        mock_module1 = Mock(spec=ModuleType)
        mock_module1.TOOL_SPEC = {"name": "tool1", "description": "First tool"}

        mock_module2 = Mock(spec=ModuleType)
        mock_module2.TOOL_SPEC = {"name": "tool2", "description": "Second tool"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[
                (None, "tool1", False),
                (None, "tool2", False),
            ],
        )

        import_mock = mocker.patch("strands_cli.tools.registry.importlib.import_module")
        import_mock.side_effect = [mock_module1, mock_module2]

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        tools = registry.list_all()
        assert len(tools) == 2
        tool_ids = {tool.id for tool in tools}
        assert tool_ids == {"tool1", "tool2"}


class TestToolRegistryResolve:
    """Tests for tool path resolution."""

    def test_resolve_direct_id(self, mocker):
        """Test resolve() with direct tool ID."""
        mock_module = Mock(spec=ModuleType)
        mock_module.TOOL_SPEC = {"name": "http_request", "description": "HTTP tool"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[(None, "http_request", False)],
        )
        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            return_value=mock_module,
        )

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        resolved = registry.resolve("http_request")
        assert resolved == "strands_cli.tools.http_request"

    def test_resolve_legacy_short_format(self, mocker):
        """Test resolve() with legacy short format (strands_tools.X)."""
        mock_module = Mock(spec=ModuleType)
        mock_module.TOOL_SPEC = {"name": "http_request", "description": "HTTP tool"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[(None, "http_request", False)],
        )
        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            return_value=mock_module,
        )

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        resolved = registry.resolve("strands_tools.http_request")
        assert resolved == "strands_cli.tools.http_request"

    def test_resolve_legacy_full_format(self, mocker):
        """Test resolve() with legacy full format (strands_tools.X.X)."""
        mock_module = Mock(spec=ModuleType)
        mock_module.TOOL_SPEC = {"name": "http_request", "description": "HTTP tool"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[(None, "http_request", False)],
        )
        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            return_value=mock_module,
        )

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        resolved = registry.resolve("strands_tools.http_request.http_request")
        assert resolved == "strands_cli.tools.http_request"

    def test_resolve_returns_none_for_unknown_tool(self, mocker):
        """Test resolve() returns None for unknown tool."""
        mocker.patch("strands_cli.tools.registry.pkgutil.iter_modules", return_value=[])

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        resolved = registry.resolve("unknown_tool")
        assert resolved is None

        resolved = registry.resolve("strands_tools.unknown_tool")
        assert resolved is None


class TestToolRegistryAllowlist:
    """Tests for allowlist generation."""

    def test_get_allowlist_includes_all_formats(self, mocker):
        """Test get_allowlist() includes all three formats for each tool."""
        mock_module = Mock(spec=ModuleType)
        mock_module.TOOL_SPEC = {"name": "http_request", "description": "HTTP tool"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[(None, "http_request", False)],
        )
        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            return_value=mock_module,
        )

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        allowlist = registry.get_allowlist()

        # Should have all four formats (short ID, full, legacy full, legacy short)
        assert "http_request" in allowlist  # Short ID
        assert "strands_cli.tools.http_request" in allowlist
        assert "strands_tools.http_request.http_request" in allowlist
        assert "strands_tools.http_request" in allowlist
        assert len(allowlist) == 4

    def test_get_allowlist_with_multiple_tools(self, mocker):
        """Test get_allowlist() with multiple tools."""
        mock_module1 = Mock(spec=ModuleType)
        mock_module1.TOOL_SPEC = {"name": "http_request", "description": "HTTP"}

        mock_module2 = Mock(spec=ModuleType)
        mock_module2.TOOL_SPEC = {"name": "file_read", "description": "File reader"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[
                (None, "http_request", False),
                (None, "file_read", False),
            ],
        )

        import_mock = mocker.patch("strands_cli.tools.registry.importlib.import_module")
        import_mock.side_effect = [mock_module1, mock_module2]

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        allowlist = registry.get_allowlist()

        # Should have 4 formats * 2 tools = 8 entries
        assert len(allowlist) == 8
        assert "strands_cli.tools.http_request" in allowlist
        assert "strands_cli.tools.file_read" in allowlist


class TestToolRegistryReset:
    """Tests for registry reset functionality."""

    def test_reset_clears_and_rediscovers(self, mocker):
        """Test _reset() clears tools and re-runs discovery."""
        mock_module = Mock(spec=ModuleType)
        mock_module.TOOL_SPEC = {"name": "test_tool", "description": "Test"}

        mocker.patch(
            "strands_cli.tools.registry.pkgutil.iter_modules",
            return_value=[(None, "test_tool", False)],
        )
        mocker.patch(
            "strands_cli.tools.registry.importlib.import_module",
            return_value=mock_module,
        )

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discover_tools()

        # Verify tool exists
        assert len(registry.list_all()) == 1

        # Manually clear and verify
        registry._tools.clear()
        assert len(registry.list_all()) == 0

        # Reset should rediscover
        registry._reset()
        assert len(registry.list_all()) == 1
