"""Unit tests for current_time native tool.

Tests the current_time tool which returns the current date and time.
"""

from datetime import UTC, datetime


class TestCurrentTimeToolSpec:
    """Test TOOL_SPEC definition for current_time."""

    def test_tool_spec_exists(self) -> None:
        """Test that TOOL_SPEC is defined in current_time module."""
        from strands_cli.tools import current_time

        assert hasattr(current_time, "TOOL_SPEC")
        assert isinstance(current_time.TOOL_SPEC, dict)

    def test_tool_spec_has_required_fields(self) -> None:
        """Test that TOOL_SPEC contains required Strands SDK fields."""
        from strands_cli.tools.current_time import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "current_time"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC

    def test_tool_spec_input_schema(self) -> None:
        """Test that TOOL_SPEC defines proper input schema."""
        from strands_cli.tools.current_time import TOOL_SPEC

        input_schema = TOOL_SPEC["inputSchema"]["json"]
        assert input_schema["type"] == "object"
        assert "format" in input_schema["properties"]
        assert "timezone" in input_schema["properties"]
        assert len(input_schema["required"]) == 0


class TestCurrentTimeFunction:
    """Test current_time function behavior."""

    def test_current_time_callable_exists(self) -> None:
        """Test that current_time function is defined and callable."""
        from strands_cli.tools.current_time import current_time

        assert callable(current_time)

    def test_default_format_iso_utc(self) -> None:
        """Test default format returns ISO timestamp in UTC."""
        from strands_cli.tools.current_time import current_time

        tool_input = {"toolUseId": "default", "input": {}}

        result = current_time(tool_input)

        assert result["toolUseId"] == "default"
        assert result["status"] == "success"
        time_str = result["content"][0]["text"]
        assert "T" in time_str
        assert len(time_str) > 10

    def test_iso_format_utc(self) -> None:
        """Test ISO format explicitly with UTC timezone."""
        from strands_cli.tools.current_time import current_time

        tool_input = {"toolUseId": "iso-utc", "input": {"format": "iso", "timezone": "utc"}}

        result = current_time(tool_input)

        assert result["status"] == "success"
        time_str = result["content"][0]["text"]
        assert "T" in time_str

    def test_iso_format_local(self) -> None:
        """Test ISO format with local timezone."""
        from strands_cli.tools.current_time import current_time

        tool_input = {"toolUseId": "iso-local", "input": {"format": "iso", "timezone": "local"}}

        result = current_time(tool_input)

        assert result["status"] == "success"
        time_str = result["content"][0]["text"]
        assert "T" in time_str

    def test_unix_format_utc(self) -> None:
        """Test Unix timestamp format."""
        from strands_cli.tools.current_time import current_time

        tool_input = {"toolUseId": "unix", "input": {"format": "unix", "timezone": "utc"}}

        result = current_time(tool_input)

        assert result["status"] == "success"
        time_str = result["content"][0]["text"]
        timestamp = int(time_str)
        assert timestamp > 1700000000
        assert timestamp < 2000000000

    def test_human_format_utc(self) -> None:
        """Test human-readable format with UTC."""
        from strands_cli.tools.current_time import current_time

        tool_input = {"toolUseId": "human-utc", "input": {"format": "human", "timezone": "utc"}}

        result = current_time(tool_input)

        assert result["status"] == "success"
        time_str = result["content"][0]["text"]
        assert "at" in time_str
        assert "UTC" in time_str

    def test_human_format_local(self) -> None:
        """Test human-readable format with local timezone."""
        from strands_cli.tools.current_time import current_time

        tool_input = {
            "toolUseId": "human-local",
            "input": {"format": "human", "timezone": "local"},
        }

        result = current_time(tool_input)

        assert result["status"] == "success"
        time_str = result["content"][0]["text"]
        assert "at" in time_str
        assert "UTC" not in time_str

    def test_invalid_format_returns_error(self) -> None:
        """Test that invalid format returns error."""
        from strands_cli.tools.current_time import current_time

        tool_input = {"toolUseId": "bad-format", "input": {"format": "invalid"}}

        result = current_time(tool_input)

        assert result["status"] == "error"
        assert "invalid format" in result["content"][0]["text"].lower()

    def test_invalid_timezone_returns_error(self) -> None:
        """Test that invalid timezone returns error."""
        from strands_cli.tools.current_time import current_time

        tool_input = {"toolUseId": "bad-tz", "input": {"timezone": "invalid"}}

        result = current_time(tool_input)

        assert result["status"] == "error"
        assert "invalid timezone" in result["content"][0]["text"].lower()

    def test_time_is_recent(self) -> None:
        """Test that returned time is reasonably recent."""
        from strands_cli.tools.current_time import current_time

        tool_input = {"toolUseId": "recent", "input": {"format": "unix", "timezone": "utc"}}

        result = current_time(tool_input)

        assert result["status"] == "success"
        timestamp = int(result["content"][0]["text"])
        now_timestamp = int(datetime.now(UTC).timestamp())
        assert abs(timestamp - now_timestamp) < 2


class TestCurrentTimeToolIntegration:
    """Test current_time tool integration with registry."""

    def test_tool_registered_in_registry(self) -> None:
        """Test that current_time is auto-discovered by registry."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        tool_info = registry.get("current_time")

        assert tool_info is not None
        assert tool_info.id == "current_time"
        assert tool_info.module_path == "strands_cli.tools.current_time"

    def test_tool_in_registry_allowlist(self) -> None:
        """Test that current_time paths are in registry allowlist."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        allowlist = registry.get_allowlist()

        assert "current_time" in allowlist
        assert "strands_cli.tools.current_time" in allowlist

    def test_registry_resolves_short_id(self) -> None:
        """Test that registry resolves short ID to full path."""
        from strands_cli.tools import get_registry

        registry = get_registry()
        resolved = registry.resolve("current_time")

        assert resolved == "strands_cli.tools.current_time"

    def test_load_python_callable_with_short_id(self) -> None:
        """Test that load_python_callable can load current_time with short ID."""
        from strands_cli.runtime.tools import load_python_callable

        tool_module = load_python_callable("current_time")

        assert hasattr(tool_module, "TOOL_SPEC")
        assert hasattr(tool_module, "current_time")
        assert callable(tool_module.current_time)
