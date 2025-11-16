"""Unit tests for duckduckgo_search native tool."""

from unittest.mock import MagicMock

from pytest_mock import MockerFixture


class TestDuckDuckGoSearchTool:
    """Tests for the duckduckgo_search tool."""

    def test_tool_spec_format(self) -> None:
        """Test that TOOL_SPEC has required fields."""
        from strands_cli.tools.duckduckgo_search import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "duckduckgo_search"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC
        assert "json" in TOOL_SPEC["inputSchema"]

        schema = TOOL_SPEC["inputSchema"]["json"]
        assert "properties" in schema
        assert "query" in schema["properties"]
        assert schema["required"] == ["query"]

        # Validate search_type enum
        search_type_prop = schema["properties"]["search_type"]
        assert search_type_prop["enum"] == ["text", "news"]
        assert search_type_prop["default"] == "text"

        # Validate max_results constraints
        max_results_prop = schema["properties"]["max_results"]
        assert max_results_prop["default"] == 10
        assert max_results_prop["minimum"] == 1
        assert max_results_prop["maximum"] == 50

        # Validate safesearch enum
        safesearch_prop = schema["properties"]["safesearch"]
        assert safesearch_prop["enum"] == ["on", "moderate", "off"]
        assert safesearch_prop["default"] == "moderate"

        # Validate timelimit enum
        timelimit_prop = schema["properties"]["timelimit"]
        assert timelimit_prop["enum"] == ["d", "w", "m", "y"]

    def test_text_search_success(self, mocker: MockerFixture) -> None:
        """Test successful text search."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS class
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = [
            {
                "title": "Python Programming",
                "href": "https://www.python.org",
                "body": "Official Python website",
            },
            {
                "title": "Python Tutorial",
                "href": "https://docs.python.org",
                "body": "Learn Python programming",
            },
        ]
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        mock_ddgs_class = mocker.patch("strands_cli.tools.duckduckgo_search.DDGS")
        mock_ddgs_class.return_value = mock_ddgs_instance

        tool = {
            "toolUseId": "test-123",
            "input": {"query": "python programming", "search_type": "text", "max_results": 2},
        }

        result = duckduckgo_search(tool)

        assert result["toolUseId"] == "test-123"
        assert result["status"] == "success"
        assert len(result["content"]) == 1
        assert "json" in result["content"][0]

        json_content = result["content"][0]["json"]
        assert json_content["query"] == "python programming"
        assert json_content["search_type"] == "text"
        assert json_content["result_count"] == 2
        assert len(json_content["results"]) == 2
        assert json_content["results"][0]["title"] == "Python Programming"

        # Verify text method was called with correct parameters
        mock_ddgs_instance.text.assert_called_once()
        call_args = mock_ddgs_instance.text.call_args
        assert call_args.args[0] == "python programming"  # First positional arg is query
        assert call_args.kwargs["max_results"] == 2
        assert call_args.kwargs["backend"] == "auto"

    def test_news_search_success(self, mocker: MockerFixture) -> None:
        """Test successful news search."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS class
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.news.return_value = [
            {
                "title": "Tech News",
                "href": "https://news.example.com/tech",
                "body": "Latest technology developments",
                "date": "2025-11-15",
                "source": "Tech Times",
            },
        ]
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        mock_ddgs_class = mocker.patch("strands_cli.tools.duckduckgo_search.DDGS")
        mock_ddgs_class.return_value = mock_ddgs_instance

        tool = {
            "toolUseId": "test-456",
            "input": {"query": "technology", "search_type": "news", "max_results": 5},
        }

        result = duckduckgo_search(tool)

        assert result["toolUseId"] == "test-456"
        assert result["status"] == "success"

        json_content = result["content"][0]["json"]
        assert json_content["search_type"] == "news"
        assert json_content["result_count"] == 1
        assert json_content["results"][0]["source"] == "Tech Times"

        # Verify news method was called
        mock_ddgs_instance.news.assert_called_once()

    def test_empty_query_error(self) -> None:
        """Test that empty query returns error."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        tool = {"toolUseId": "test-789", "input": {"query": ""}}

        result = duckduckgo_search(tool)

        assert result["toolUseId"] == "test-789"
        assert result["status"] == "error"
        assert "No search query provided" in result["content"][0]["text"]

    def test_whitespace_only_query_error(self) -> None:
        """Test that whitespace-only query returns error."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        tool = {"toolUseId": "test-abc", "input": {"query": "   "}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "No search query provided" in result["content"][0]["text"]

    def test_missing_query_error(self) -> None:
        """Test that missing query returns error."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        tool = {"toolUseId": "test-def", "input": {}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "No search query provided" in result["content"][0]["text"]

    def test_invalid_max_results_too_low(self) -> None:
        """Test that max_results below minimum returns error."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        tool = {"toolUseId": "test-ghi", "input": {"query": "test", "max_results": 0}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "max_results must be between 1 and 50" in result["content"][0]["text"]

    def test_invalid_max_results_too_high(self) -> None:
        """Test that max_results above maximum returns error."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        tool = {"toolUseId": "test-jkl", "input": {"query": "test", "max_results": 51}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "max_results must be between 1 and 50" in result["content"][0]["text"]

    def test_invalid_max_results_not_integer(self) -> None:
        """Test that non-integer max_results returns error."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        tool = {"toolUseId": "test-mno", "input": {"query": "test", "max_results": "ten"}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "max_results must be between 1 and 50" in result["content"][0]["text"]

    def test_invalid_search_type(self, mocker: MockerFixture) -> None:
        """Test that invalid search_type returns error."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS to avoid import issues
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mocker.patch("strands_cli.tools.duckduckgo_search.DDGS", return_value=mock_ddgs_instance)

        tool = {"toolUseId": "test-pqr", "input": {"query": "test", "search_type": "invalid"}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "Invalid search_type" in result["content"][0]["text"]

    def test_default_parameters(self, mocker: MockerFixture) -> None:
        """Test that default parameters are applied correctly."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS class
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = [
            {"title": "Test", "href": "http://test.com", "body": "Test"}
        ]
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        mock_ddgs_class = mocker.patch("strands_cli.tools.duckduckgo_search.DDGS")
        mock_ddgs_class.return_value = mock_ddgs_instance

        tool = {"toolUseId": "test-stu", "input": {"query": "test query"}}

        result = duckduckgo_search(tool)

        assert result["status"] == "success"

        # Verify defaults were applied
        call_args = mock_ddgs_instance.text.call_args
        assert call_args.args[0] == "test query"  # First positional arg is query
        assert call_args.kwargs["max_results"] == 10  # default
        assert call_args.kwargs["region"] == "us-en"  # default
        assert call_args.kwargs["safesearch"] == "moderate"  # default
        assert call_args.kwargs["backend"] == "auto"

    def test_timelimit_parameter(self, mocker: MockerFixture) -> None:
        """Test that timelimit parameter is passed correctly."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS class
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = []
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        mock_ddgs_class = mocker.patch("strands_cli.tools.duckduckgo_search.DDGS")
        mock_ddgs_class.return_value = mock_ddgs_instance

        tool = {
            "toolUseId": "test-vwx",
            "input": {"query": "recent news", "search_type": "text", "timelimit": "w"},
        }

        result = duckduckgo_search(tool)

        assert result["status"] == "success"

        # Verify timelimit was passed
        call_args = mock_ddgs_instance.text.call_args
        assert call_args.kwargs["timelimit"] == "w"

    def test_custom_region_and_safesearch(self, mocker: MockerFixture) -> None:
        """Test that custom region and safesearch are applied."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS class
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = []
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        mock_ddgs_class = mocker.patch("strands_cli.tools.duckduckgo_search.DDGS")
        mock_ddgs_class.return_value = mock_ddgs_instance

        tool = {
            "toolUseId": "test-yz1",
            "input": {"query": "test", "region": "uk-en", "safesearch": "off"},
        }

        result = duckduckgo_search(tool)

        assert result["status"] == "success"

        call_args = mock_ddgs_instance.text.call_args
        assert call_args.kwargs["region"] == "uk-en"
        assert call_args.kwargs["safesearch"] == "off"

    def test_rate_limit_exception(self, mocker: MockerFixture) -> None:
        """Test handling of rate limit exceptions."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS to raise a rate limit error
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.side_effect = Exception("Ratelimit error: Too many requests")
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        mocker.patch("strands_cli.tools.duckduckgo_search.DDGS", return_value=mock_ddgs_instance)

        tool = {"toolUseId": "test-234", "input": {"query": "test"}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "Rate limit exceeded" in result["content"][0]["text"]
        assert "automatically retry" in result["content"][0]["text"]

    def test_timeout_exception(self, mocker: MockerFixture) -> None:
        """Test handling of timeout exceptions."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS to raise a timeout error
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.side_effect = Exception("Timeout error: Request took too long")
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        mocker.patch("strands_cli.tools.duckduckgo_search.DDGS", return_value=mock_ddgs_instance)

        tool = {"toolUseId": "test-567", "input": {"query": "test"}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "Search timed out" in result["content"][0]["text"]
        assert "reducing max_results" in result["content"][0]["text"]

    def test_generic_exception(self, mocker: MockerFixture) -> None:
        """Test handling of generic exceptions."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS to raise a generic error
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.side_effect = ValueError("Invalid parameter")
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        mocker.patch("strands_cli.tools.duckduckgo_search.DDGS", return_value=mock_ddgs_instance)

        tool = {"toolUseId": "test-890", "input": {"query": "test"}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "Search failed" in result["content"][0]["text"]
        assert "ValueError" in result["content"][0]["text"]

    def test_import_error(self, mocker: MockerFixture) -> None:
        """Test handling when ddgs library is not installed."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS_AVAILABLE to False to simulate missing library
        mocker.patch("strands_cli.tools.duckduckgo_search.DDGS_AVAILABLE", False)

        tool = {"toolUseId": "test-abc123", "input": {"query": "test"}}

        result = duckduckgo_search(tool)

        assert result["status"] == "error"
        assert "ddgs library not installed" in result["content"][0]["text"]

    def test_empty_results(self, mocker: MockerFixture) -> None:
        """Test handling of empty search results."""
        from strands_cli.tools.duckduckgo_search import duckduckgo_search

        # Mock DDGS to return empty results
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = []
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        mocker.patch("strands_cli.tools.duckduckgo_search.DDGS", return_value=mock_ddgs_instance)

        tool = {"toolUseId": "test-empty", "input": {"query": "xyzabc123notfound"}}

        result = duckduckgo_search(tool)

        assert result["status"] == "success"
        json_content = result["content"][0]["json"]
        assert json_content["result_count"] == 0
        assert json_content["results"] == []
