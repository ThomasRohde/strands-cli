"""Unit tests for tavily_search native tool."""

from unittest.mock import MagicMock

from pytest_mock import MockerFixture


class TestTavilySearchTool:
    """Tests for the tavily_search tool."""

    def test_tool_spec_format(self) -> None:
        """Test that TOOL_SPEC has required fields."""
        from strands_cli.tools.tavily_search import TOOL_SPEC

        assert "name" in TOOL_SPEC
        assert TOOL_SPEC["name"] == "tavily_search"
        assert "description" in TOOL_SPEC
        assert "inputSchema" in TOOL_SPEC
        assert "json" in TOOL_SPEC["inputSchema"]

        schema = TOOL_SPEC["inputSchema"]["json"]
        assert "properties" in schema
        assert "query" in schema["properties"]
        assert schema["required"] == ["query"]

        # Validate max_results constraints
        max_results_prop = schema["properties"]["max_results"]
        assert max_results_prop["default"] == 5
        assert max_results_prop["minimum"] == 1
        assert max_results_prop["maximum"] == 20

        # Validate include_answer
        include_answer_prop = schema["properties"]["include_answer"]
        assert include_answer_prop["type"] == "boolean"
        assert include_answer_prop["default"] is False

    def test_search_success(self, mocker: MockerFixture) -> None:
        """Test successful search."""
        from strands_cli.tools.tavily_search import tavily_search

        # Mock TavilyClient class
        mock_client_instance = MagicMock()
        mock_client_instance.search.return_value = {
            "query": "artificial intelligence",
            "results": [
                {
                    "title": "AI Overview",
                    "url": "https://example.com/ai",
                    "content": "Artificial intelligence overview and introduction",
                    "score": 0.95,
                },
                {
                    "title": "Machine Learning Basics",
                    "url": "https://example.com/ml",
                    "content": "Introduction to machine learning concepts",
                    "score": 0.88,
                },
            ],
            "response_time": 0.42,
        }

        mock_client_class = mocker.patch("strands_cli.tools.tavily_search.TavilyClient")
        mock_client_class.return_value = mock_client_instance

        # Mock environment variable
        mocker.patch("os.environ.get", return_value="tvly-test-api-key")

        tool = {
            "toolUseId": "test-456",
            "input": {"query": "artificial intelligence", "max_results": 5},
        }

        result = tavily_search(tool)

        assert result["toolUseId"] == "test-456"
        assert result["status"] == "success"
        assert len(result["content"]) == 1
        assert "json" in result["content"][0]

        json_content = result["content"][0]["json"]
        assert json_content["query"] == "artificial intelligence"
        assert len(json_content["results"]) == 2
        assert json_content["results"][0]["title"] == "AI Overview"
        assert json_content["results"][0]["score"] == 0.95
        assert "response_time" in json_content

        # Verify search method was called with correct parameters
        mock_client_instance.search.assert_called_once_with(
            query="artificial intelligence",
            max_results=5,
            include_answer=False,
        )

        # Verify API key was used
        mock_client_class.assert_called_once_with(api_key="tvly-test-api-key")

    def test_search_with_answer(self, mocker: MockerFixture) -> None:
        """Test search with AI-generated answer."""
        from strands_cli.tools.tavily_search import tavily_search

        # Mock TavilyClient class
        mock_client_instance = MagicMock()
        mock_client_instance.search.return_value = {
            "query": "what is photosynthesis",
            "results": [
                {
                    "title": "Photosynthesis Explained",
                    "url": "https://example.com/photosynthesis",
                    "content": "Process by which plants convert light into energy",
                    "score": 0.92,
                }
            ],
            "answer": "Photosynthesis is the process by which plants use sunlight, water, and carbon dioxide to produce oxygen and energy in the form of sugar.",
            "response_time": 0.58,
        }

        mock_client_class = mocker.patch("strands_cli.tools.tavily_search.TavilyClient")
        mock_client_class.return_value = mock_client_instance

        # Mock environment variable
        mocker.patch("os.environ.get", return_value="tvly-test-api-key")

        tool = {
            "toolUseId": "test-789",
            "input": {
                "query": "what is photosynthesis",
                "max_results": 3,
                "include_answer": True,
            },
        }

        result = tavily_search(tool)

        assert result["status"] == "success"
        json_content = result["content"][0]["json"]
        assert "answer" in json_content
        assert "Photosynthesis" in json_content["answer"]

        # Verify include_answer was passed
        mock_client_instance.search.assert_called_once_with(
            query="what is photosynthesis",
            max_results=3,
            include_answer=True,
        )

    def test_empty_query_error(self, mocker: MockerFixture) -> None:
        """Test error handling for empty query."""
        from strands_cli.tools.tavily_search import tavily_search

        tool = {"toolUseId": "test-empty", "input": {"query": ""}}

        result = tavily_search(tool)

        assert result["toolUseId"] == "test-empty"
        assert result["status"] == "error"
        assert "No search query provided" in result["content"][0]["text"]

    def test_missing_query_error(self, mocker: MockerFixture) -> None:
        """Test error handling for missing query."""
        from strands_cli.tools.tavily_search import tavily_search

        tool = {"toolUseId": "test-missing", "input": {}}

        result = tavily_search(tool)

        assert result["toolUseId"] == "test-missing"
        assert result["status"] == "error"
        assert "No search query provided" in result["content"][0]["text"]

    def test_invalid_max_results_too_low(self, mocker: MockerFixture) -> None:
        """Test error handling for max_results below minimum."""
        from strands_cli.tools.tavily_search import tavily_search

        tool = {
            "toolUseId": "test-invalid-low",
            "input": {"query": "test", "max_results": 0},
        }

        result = tavily_search(tool)

        assert result["status"] == "error"
        assert "max_results must be between 1 and 20" in result["content"][0]["text"]

    def test_invalid_max_results_too_high(self, mocker: MockerFixture) -> None:
        """Test error handling for max_results above maximum."""
        from strands_cli.tools.tavily_search import tavily_search

        tool = {
            "toolUseId": "test-invalid-high",
            "input": {"query": "test", "max_results": 25},
        }

        result = tavily_search(tool)

        assert result["status"] == "error"
        assert "max_results must be between 1 and 20" in result["content"][0]["text"]

    def test_invalid_max_results_not_integer(self, mocker: MockerFixture) -> None:
        """Test error handling for non-integer max_results."""
        from strands_cli.tools.tavily_search import tavily_search

        tool = {
            "toolUseId": "test-invalid-type",
            "input": {"query": "test", "max_results": "five"},
        }

        result = tavily_search(tool)

        assert result["status"] == "error"
        assert "max_results must be between 1 and 20" in result["content"][0]["text"]

    def test_library_not_available(self, mocker: MockerFixture) -> None:
        """Test graceful handling when tavily-python not installed."""
        from strands_cli.tools import tavily_search

        # Mock TAVILY_AVAILABLE to False
        mocker.patch.object(tavily_search, "TAVILY_AVAILABLE", False)

        tool = {
            "toolUseId": "test-no-lib",
            "input": {"query": "test query"},
        }

        result = tavily_search.tavily_search(tool)

        assert result["status"] == "error"
        assert "tavily-python library not installed" in result["content"][0]["text"]
        assert "pip install tavily-python" in result["content"][0]["text"]

    def test_api_key_missing(self, mocker: MockerFixture) -> None:
        """Test error handling when TAVILY_API_KEY not set."""
        from strands_cli.tools.tavily_search import tavily_search

        # Mock environment variable to return None
        mocker.patch("os.environ.get", return_value=None)

        tool = {
            "toolUseId": "test-no-key",
            "input": {"query": "test query"},
        }

        result = tavily_search(tool)

        assert result["status"] == "error"
        assert "TAVILY_API_KEY environment variable not set" in result["content"][0]["text"]
        assert "https://app.tavily.com" in result["content"][0]["text"]

    def test_authentication_error(self, mocker: MockerFixture) -> None:
        """Test error handling for authentication failures."""
        from strands_cli.tools.tavily_search import tavily_search

        # Mock TavilyClient to raise authentication error
        mock_client_instance = MagicMock()
        mock_client_instance.search.side_effect = Exception("Invalid API key provided")

        mock_client_class = mocker.patch("strands_cli.tools.tavily_search.TavilyClient")
        mock_client_class.return_value = mock_client_instance

        # Mock environment variable
        mocker.patch("os.environ.get", return_value="invalid-key")

        tool = {
            "toolUseId": "test-auth-error",
            "input": {"query": "test query"},
        }

        result = tavily_search(tool)

        assert result["status"] == "error"
        assert "Authentication failed" in result["content"][0]["text"]
        assert "TAVILY_API_KEY is valid" in result["content"][0]["text"]

    def test_rate_limit_error(self, mocker: MockerFixture) -> None:
        """Test error handling for rate limit errors."""
        from strands_cli.tools.tavily_search import tavily_search

        # Mock TavilyClient to raise rate limit error
        mock_client_instance = MagicMock()
        mock_client_instance.search.side_effect = Exception("Rate limit exceeded")

        mock_client_class = mocker.patch("strands_cli.tools.tavily_search.TavilyClient")
        mock_client_class.return_value = mock_client_instance

        # Mock environment variable
        mocker.patch("os.environ.get", return_value="tvly-test-key")

        tool = {
            "toolUseId": "test-rate-limit",
            "input": {"query": "test query"},
        }

        result = tavily_search(tool)

        assert result["status"] == "error"
        assert "Rate limit" in result["content"][0]["text"]
        assert "https://app.tavily.com" in result["content"][0]["text"]

    def test_timeout_error(self, mocker: MockerFixture) -> None:
        """Test error handling for timeout errors."""
        from strands_cli.tools.tavily_search import tavily_search

        # Mock TavilyClient to raise timeout error
        mock_client_instance = MagicMock()
        mock_client_instance.search.side_effect = Exception("Request timeout")

        mock_client_class = mocker.patch("strands_cli.tools.tavily_search.TavilyClient")
        mock_client_class.return_value = mock_client_instance

        # Mock environment variable
        mocker.patch("os.environ.get", return_value="tvly-test-key")

        tool = {
            "toolUseId": "test-timeout",
            "input": {"query": "test query"},
        }

        result = tavily_search(tool)

        assert result["status"] == "error"
        assert "timed out" in result["content"][0]["text"]

    def test_generic_error(self, mocker: MockerFixture) -> None:
        """Test error handling for generic exceptions."""
        from strands_cli.tools.tavily_search import tavily_search

        # Mock TavilyClient to raise generic error
        mock_client_instance = MagicMock()
        mock_client_instance.search.side_effect = ValueError("Unexpected error")

        mock_client_class = mocker.patch("strands_cli.tools.tavily_search.TavilyClient")
        mock_client_class.return_value = mock_client_instance

        # Mock environment variable
        mocker.patch("os.environ.get", return_value="tvly-test-key")

        tool = {
            "toolUseId": "test-generic-error",
            "input": {"query": "test query"},
        }

        result = tavily_search(tool)

        assert result["status"] == "error"
        assert "Search failed" in result["content"][0]["text"]
        assert "ValueError" in result["content"][0]["text"]

    def test_empty_results(self, mocker: MockerFixture) -> None:
        """Test handling of empty search results."""
        from strands_cli.tools.tavily_search import tavily_search

        # Mock TavilyClient to return empty results
        mock_client_instance = MagicMock()
        mock_client_instance.search.return_value = {
            "query": "extremely obscure query",
            "results": [],
            "response_time": 0.23,
        }

        mock_client_class = mocker.patch("strands_cli.tools.tavily_search.TavilyClient")
        mock_client_class.return_value = mock_client_instance

        # Mock environment variable
        mocker.patch("os.environ.get", return_value="tvly-test-key")

        tool = {
            "toolUseId": "test-empty-results",
            "input": {"query": "extremely obscure query"},
        }

        result = tavily_search(tool)

        assert result["status"] == "success"
        json_content = result["content"][0]["json"]
        assert json_content["results"] == []
        assert json_content["query"] == "extremely obscure query"
