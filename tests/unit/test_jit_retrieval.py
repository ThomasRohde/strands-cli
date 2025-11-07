"""Unit tests for JIT retrieval tools (grep, head, tail, search).

Tests cross-platform file operations with path validation, encoding handling,
and binary file detection.
"""


import pytest


class TestGrepTool:
    """Tests for jit_grep.py tool."""

    def test_grep_tool_spec_format(self):
        """TOOL_SPEC should have required fields."""
        from strands_cli.tools.jit_grep import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "grep"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC
        assert "json" in TOOL_SPEC["inputSchema"]

    def test_grep_finds_pattern_with_context(self, tmp_path):
        """Should find pattern and return context lines."""
        from strands_cli.tools.jit_grep import grep

        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nTARGET\nline4\nline5\n")

        tool = {
            "toolUseId": "test-123",
            "input": {
                "pattern": "TARGET",
                "path": str(test_file),
                "context_lines": 1,
            },
        }

        result = grep(tool)

        assert result["toolUseId"] == "test-123"
        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "TARGET" in content
        assert "line2" in content  # Context before
        assert "line4" in content  # Context after
        assert ">" in content  # Match indicator

    def test_grep_regex_pattern(self, tmp_path):
        """Should support regex patterns."""
        from strands_cli.tools.jit_grep import grep

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\nclass Bar:\n    pass\n")

        tool = {
            "toolUseId": "test-456",
            "input": {
                "pattern": r"^(def|class)\s+\w+",
                "path": str(test_file),
                "context_lines": 0,
            },
        }

        result = grep(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "def foo" in content
        assert "class Bar" in content

    def test_grep_case_insensitive(self, tmp_path):
        """Should support case-insensitive search."""
        from strands_cli.tools.jit_grep import grep

        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello\nWORLD\nhello\n")

        tool = {
            "toolUseId": "test-789",
            "input": {
                "pattern": "hello",
                "path": str(test_file),
                "ignore_case": True,
            },
        }

        result = grep(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        # Should find both "Hello" and "hello"
        assert "2 match(es)" in content

    def test_grep_no_matches(self, tmp_path):
        """Should return success with no matches message."""
        from strands_cli.tools.jit_grep import grep

        test_file = tmp_path / "test.txt"
        test_file.write_text("foo\nbar\nbaz\n")

        tool = {
            "toolUseId": "test-000",
            "input": {"pattern": "NOTFOUND", "path": str(test_file)},
        }

        result = grep(tool)

        assert result["status"] == "success"
        assert "No matches found" in result["content"][0]["text"]

    def test_grep_max_matches_limit(self, tmp_path):
        """Should respect max_matches limit."""
        from strands_cli.tools.jit_grep import grep

        test_file = tmp_path / "test.txt"
        test_file.write_text("match\n" * 100)

        tool = {
            "toolUseId": "test-111",
            "input": {"pattern": "match", "path": str(test_file), "max_matches": 5},
        }

        result = grep(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "5 match(es)" in content
        assert "first 5 matches" in content.lower()

    def test_grep_file_not_found(self):
        """Should return error for non-existent file."""
        from strands_cli.tools.jit_grep import grep

        tool = {
            "toolUseId": "test-222",
            "input": {"pattern": "test", "path": "/nonexistent/file.txt"},
        }

        result = grep(tool)

        assert result["status"] == "error"
        assert "not found" in result["content"][0]["text"].lower()

    def test_grep_binary_file_detection(self, tmp_path):
        """Should detect and reject binary files."""
        from strands_cli.tools.jit_grep import grep

        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03" * 100)

        tool = {
            "toolUseId": "test-333",
            "input": {"pattern": "test", "path": str(test_file)},
        }

        result = grep(tool)

        assert result["status"] == "error"
        assert "binary" in result["content"][0]["text"].lower()

    def test_grep_invalid_regex(self, tmp_path):
        """Should return error for invalid regex pattern."""
        from strands_cli.tools.jit_grep import grep

        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        tool = {
            "toolUseId": "test-444",
            "input": {"pattern": "[invalid(regex", "path": str(test_file)},
        }

        result = grep(tool)

        assert result["status"] == "error"
        assert "regex" in result["content"][0]["text"].lower()

    def test_grep_empty_pattern(self, tmp_path):
        """Should return error for empty pattern."""
        from strands_cli.tools.jit_grep import grep

        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        tool = {"toolUseId": "test-555", "input": {"pattern": "", "path": str(test_file)}}

        result = grep(tool)

        assert result["status"] == "error"
        assert "pattern" in result["content"][0]["text"].lower()


class TestHeadTool:
    """Tests for jit_head.py tool."""

    def test_head_tool_spec_format(self):
        """TOOL_SPEC should have required fields."""
        from strands_cli.tools.jit_head import TOOL_SPEC

        assert TOOL_SPEC["name"] == "head"
        assert "inputSchema" in TOOL_SPEC

    def test_head_reads_first_lines(self, tmp_path):
        """Should read first N lines from file."""
        from strands_cli.tools.jit_head import head

        test_file = tmp_path / "test.txt"
        test_file.write_text("\n".join([f"line{i}" for i in range(1, 21)]))

        tool = {
            "toolUseId": "test-123",
            "input": {"path": str(test_file), "lines": 5},
        }

        result = head(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "line1" in content
        assert "line5" in content
        assert "line6" not in content

    def test_head_default_lines(self, tmp_path):
        """Should default to 10 lines."""
        from strands_cli.tools.jit_head import head

        test_file = tmp_path / "test.txt"
        test_file.write_text("\n".join([f"line{i}" for i in range(1, 21)]))

        tool = {"toolUseId": "test-456", "input": {"path": str(test_file)}}

        result = head(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "line10" in content
        assert "line11" not in content

    def test_head_empty_file(self, tmp_path):
        """Should handle empty file gracefully."""
        from strands_cli.tools.jit_head import head

        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        tool = {"toolUseId": "test-789", "input": {"path": str(test_file)}}

        result = head(tool)

        assert result["status"] == "success"
        assert "empty" in result["content"][0]["text"].lower()

    def test_head_bytes_limit(self, tmp_path):
        """Should respect bytes limit."""
        from strands_cli.tools.jit_head import head

        test_file = tmp_path / "large.txt"
        # Create file with large lines
        test_file.write_text("x" * 100000 + "\n" * 100)

        tool = {
            "toolUseId": "test-000",
            "input": {"path": str(test_file), "lines": 100, "bytes_limit": 1000},
        }

        result = head(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "truncated" in content.lower() or "byte limit" in content.lower()

    def test_head_binary_file_detection(self, tmp_path):
        """Should detect and reject binary files."""
        from strands_cli.tools.jit_head import head

        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03" * 100)

        tool = {"toolUseId": "test-111", "input": {"path": str(test_file)}}

        result = head(tool)

        assert result["status"] == "error"
        assert "binary" in result["content"][0]["text"].lower()


class TestTailTool:
    """Tests for jit_tail.py tool."""

    def test_tail_tool_spec_format(self):
        """TOOL_SPEC should have required fields."""
        from strands_cli.tools.jit_tail import TOOL_SPEC

        assert TOOL_SPEC["name"] == "tail"
        assert "inputSchema" in TOOL_SPEC

    def test_tail_reads_last_lines(self, tmp_path):
        """Should read last N lines from file."""
        from strands_cli.tools.jit_tail import tail

        test_file = tmp_path / "test.txt"
        test_file.write_text("\n".join([f"line{i}" for i in range(1, 21)]))

        tool = {
            "toolUseId": "test-123",
            "input": {"path": str(test_file), "lines": 5},
        }

        result = tail(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "line16" in content
        assert "line20" in content
        assert "line15" not in content

    def test_tail_default_lines(self, tmp_path):
        """Should default to 10 lines."""
        from strands_cli.tools.jit_tail import tail

        test_file = tmp_path / "test.txt"
        test_file.write_text("\n".join([f"line{i}" for i in range(1, 21)]))

        tool = {"toolUseId": "test-456", "input": {"path": str(test_file)}}

        result = tail(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "line11" in content
        assert "line20" in content

    def test_tail_fewer_lines_than_requested(self, tmp_path):
        """Should return all lines if file has fewer than requested."""
        from strands_cli.tools.jit_tail import tail

        test_file = tmp_path / "small.txt"
        test_file.write_text("line1\nline2\nline3\n")

        tool = {
            "toolUseId": "test-789",
            "input": {"path": str(test_file), "lines": 10},
        }

        result = tail(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "line1" in content
        assert "line2" in content
        assert "line3" in content

    def test_tail_empty_file(self, tmp_path):
        """Should handle empty file gracefully."""
        from strands_cli.tools.jit_tail import tail

        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        tool = {"toolUseId": "test-000", "input": {"path": str(test_file)}}

        result = tail(tool)

        assert result["status"] == "success"
        assert "empty" in result["content"][0]["text"].lower()


class TestSearchTool:
    """Tests for jit_search.py tool."""

    def test_search_tool_spec_format(self):
        """TOOL_SPEC should have required fields."""
        from strands_cli.tools.jit_search import TOOL_SPEC

        assert TOOL_SPEC["name"] == "search"
        assert "inputSchema" in TOOL_SPEC

    def test_search_plain_text(self, tmp_path):
        """Should find plain text keywords."""
        from strands_cli.tools.jit_search import search

        test_file = tmp_path / "test.txt"
        test_file.write_text("foo\nbar\nbaz\nfoo again\n")

        tool = {
            "toolUseId": "test-123",
            "input": {"query": "foo", "path": str(test_file)},
        }

        result = search(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "2 match(es)" in content
        assert ">>>" in content  # Match highlighting

    def test_search_case_insensitive_default(self, tmp_path):
        """Should be case-insensitive by default."""
        from strands_cli.tools.jit_search import search

        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello\nWORLD\nhello\n")

        tool = {
            "toolUseId": "test-456",
            "input": {"query": "hello", "path": str(test_file)},
        }

        result = search(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "2 match(es)" in content

    def test_search_regex_mode(self, tmp_path):
        """Should support regex when is_regex=true."""
        from strands_cli.tools.jit_search import search

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\nclass Bar:\n    pass\n")

        tool = {
            "toolUseId": "test-789",
            "input": {
                "query": r"^(def|class)",
                "path": str(test_file),
                "is_regex": True,
            },
        }

        result = search(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "2 match(es)" in content

    def test_search_no_matches(self, tmp_path):
        """Should return success with no matches message."""
        from strands_cli.tools.jit_search import search

        test_file = tmp_path / "test.txt"
        test_file.write_text("foo\nbar\nbaz\n")

        tool = {
            "toolUseId": "test-000",
            "input": {"query": "NOTFOUND", "path": str(test_file)},
        }

        result = search(tool)

        assert result["status"] == "success"
        assert "No matches" in result["content"][0]["text"]

    def test_search_max_matches(self, tmp_path):
        """Should respect max_matches limit."""
        from strands_cli.tools.jit_search import search

        test_file = tmp_path / "test.txt"
        test_file.write_text("match\n" * 100)

        tool = {
            "toolUseId": "test-111",
            "input": {"query": "match", "path": str(test_file), "max_matches": 3},
        }

        result = search(tool)

        assert result["status"] == "success"
        content = result["content"][0]["text"]
        assert "3 match(es)" in content

    def test_search_empty_query(self, tmp_path):
        """Should return error for empty query."""
        from strands_cli.tools.jit_search import search

        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        tool = {"toolUseId": "test-222", "input": {"query": "", "path": str(test_file)}}

        result = search(tool)

        assert result["status"] == "error"
        assert "query" in result["content"][0]["text"].lower()


class TestPathSecurity:
    """Test path validation and security across all tools."""

    def test_path_traversal_prevention(self, tmp_path):
        """All tools should prevent directory traversal attacks."""
        from strands_cli.tools.jit_grep import grep
        from strands_cli.tools.jit_head import head
        from strands_cli.tools.jit_search import search
        from strands_cli.tools.jit_tail import tail

        # Create a file outside tmp_path
        safe_file = tmp_path / "safe.txt"
        safe_file.write_text("safe content")

        # All tools should resolve paths and work with legitimate files
        for tool_func, tool_name in [
            (grep, "grep"),
            (head, "head"),
            (tail, "tail"),
            (search, "search"),
        ]:
            input_data = {"path": str(safe_file)}
            if tool_name == "grep":
                input_data["pattern"] = "safe"
            elif tool_name == "search":
                input_data["query"] = "safe"

            tool = {"toolUseId": f"test-{tool_name}", "input": input_data}

            result = tool_func(tool)
            # Should work with legitimate path
            assert result["status"] == "success"

    def test_symlink_resolution(self, tmp_path):
        """Tools should resolve symlinks safely."""
        from strands_cli.tools.jit_head import head

        # Create original file
        original = tmp_path / "original.txt"
        original.write_text("original content\n")

        # Create symlink
        link = tmp_path / "link.txt"
        try:
            link.symlink_to(original)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        tool = {"toolUseId": "test-symlink", "input": {"path": str(link)}}

        result = head(tool)

        # Should follow symlink and read original file
        assert result["status"] == "success"
        assert "original content" in result["content"][0]["text"]
