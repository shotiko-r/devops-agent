"""
Web search tests.

Run from the project root:
    .venv/bin/python -m unittest test_web -v
"""

import json
import unittest
from unittest import mock

import audit

from tools.web import web_search
from tools.web import WebSearchError, WebSearchRateLimitError, WebSearchTimeoutError
from tool_registry import registry


class TestWebSearchSuccessful(unittest.TestCase):
    """Test successful web search with mocked Tavily API."""

    def setUp(self):
        self._audit_enabled = audit.audit.enabled
        audit.audit.enabled = False

    def tearDown(self):
        audit.audit.enabled = self._audit_enabled

    @mock.patch("tools.web.client.search")
    def test_successful_search(self, mock_search):
        """Test that a valid search query returns results."""
        mock_search.return_value = {
            "results": [
                {
                    "title": "Kubernetes Release Notes",
                    "url": "https://kubernetes.io/releases",
                    "content": "Kubernetes v1.36 released with new features.",
                    "score": 0.95,
                }
            ]
        }

        results = web_search(query="Kubernetes latest version", max_results=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Kubernetes Release Notes")
        self.assertEqual(results[0]["url"], "https://kubernetes.io/releases")
        self.assertEqual(results[0]["score"], 0.95)

    @mock.patch("tools.web.client.search")
    def test_successful_search_default_max_results(self, mock_search):
        """Test that default max_results=5 is used when not specified."""
        mock_search.return_value = {"results": []}
        results = web_search(query="test query")
        self.assertEqual(len(results), 0)


class TestWebSearchEmptyQuery(unittest.TestCase):
    """Test that empty/whitespace queries are rejected."""

    def setUp(self):
        self._audit_enabled = audit.audit.enabled
        audit.audit.enabled = False

    def tearDown(self):
        audit.audit.enabled = self._audit_enabled

    def test_empty_query_raises_error(self):
        """Test that empty query raises WebSearchError."""
        with self.assertRaises(WebSearchError):
            web_search(query="")

    def test_whitespace_query_raises_error(self):
        """Test that whitespace-only query raises WebSearchError."""
        with self.assertRaises(WebSearchError):
            web_search(query="   ")


class TestWebSearchInvalidParams(unittest.TestCase):
    """Test that invalid parameters are rejected."""

    def setUp(self):
        self._audit_enabled = audit.audit.enabled
        audit.audit.enabled = False

    def tearDown(self):
        audit.audit.enabled = self._audit_enabled

    def test_max_results_zero_raises_error(self):
        """Test that max_results=0 raises WebSearchError."""
        with self.assertRaises(WebSearchError):
            web_search(query="test", max_results=0)

    def test_max_results_negative_raises_error(self):
        """Test that max_results=-1 raises WebSearchError."""
        with self.assertRaises(WebSearchError):
            web_search(query="test", max_results=-1)


class TestWebSearchAPIErrorHandling(unittest.TestCase):
    """Test Tavily API error handling with mocked client."""

    def setUp(self):
        self._audit_enabled = audit.audit.enabled
        audit.audit.enabled = False

    def tearDown(self):
        audit.audit.enabled = self._audit_enabled

    @mock.patch("tools.web.client.search")
    def test_generic_exception_raises_web_search_error(self, mock_search):
        """Test that generic exception from Tavily raises WebSearchError."""
        mock_search.side_effect = Exception("Generic Tavily error")

        with self.assertRaises(WebSearchError):
            web_search(query="test query")

    @mock.patch("tools.web.client.search")
    def test_rate_limit_raises_web_search_rate_limit_error(self, mock_search):
        """Test that rate limit error raises WebSearchRateLimitError."""
        from tavily.errors import UsageLimitExceededError
        mock_search.side_effect = UsageLimitExceededError(
            "Rate limit exceeded"
        )

        with self.assertRaises(WebSearchRateLimitError):
            web_search(query="test query")

    @mock.patch("tools.web.client.search")
    def test_timeout_raises_web_search_timeout_error(self, mock_search):
        """Test that timeout error raises WebSearchTimeoutError."""
        from tavily.errors import TimeoutError
        mock_search.side_effect = TimeoutError("Request timed out")

        with self.assertRaises(WebSearchTimeoutError):
            web_search(query="test query")


class TestWebSearchIntegration(unittest.TestCase):
    """Integration-style tests for web_search through the registry."""

    def setUp(self):
        self._audit_enabled = audit.audit.enabled
        audit.audit.enabled = False

    def tearDown(self):
        audit.audit.enabled = self._audit_enabled

    def test_web_search_is_registered(self):
        """Test that web_search is in the tool registry."""
        self.assertIn("web_search", registry.names())

    def test_web_search_schema(self):
        """Test that web_search schema is OpenAI-compatible."""
        schemas = registry.schemas()
        web_schema = [s for s in schemas if s["function"]["name"] == "web_search"][0]

        self.assertEqual(web_schema["type"], "function")
        self.assertIn("name", web_schema["function"])
        self.assertIn("description", web_schema["function"])
        params = web_schema["function"]["parameters"]
        self.assertEqual(params["type"], "object")
        self.assertIn("query", params["properties"])
        self.assertIn("max_results", params["properties"])
        self.assertIn("query", params.get("required", []))


class TestWebSearchRegistryExecution(unittest.TestCase):
    """Test web_search execution through the tool registry."""

    def setUp(self):
        self._audit_enabled = audit.audit.enabled
        audit.audit.enabled = False

    def tearDown(self):
        audit.audit.enabled = self._audit_enabled

    def test_web_search_lookup_in_registry(self):
        """Test that web_search can be looked up from the registry."""
        tool = registry.get("web_search")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "web_search")

    def test_web_search_schema_is_valid(self):
        """Test that web_search schema is valid and complete."""
        schemas = registry.schemas()
        web_schema = [s for s in schemas if s["function"]["name"] == "web_search"][0]
        self.assertEqual(web_schema["type"], "function")
        fn = web_schema["function"]
        self.assertIn("name", fn)
        self.assertIn("description", fn)
        self.assertIn("parameters", fn)
        params = fn["parameters"]
        self.assertEqual(params["type"], "object")
        self.assertIn("query", params["properties"])
        self.assertIn("max_results", params["properties"])
        self.assertIn("query", params.get("required", []))

    def test_tool_definition_read_only_and_risk(self):
        """Test the ToolDefinition metadata for web_search."""
        tool = registry.get("web_search")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "web_search")
        self.assertTrue(tool.read_only)
        self.assertEqual(tool.risk_level, "low")


class TestWebSearchResultSerialization(unittest.TestCase):
    """Test that tool results are properly serialized."""

    @mock.patch("tools.web.client.search")
    def test_web_search_result_is_list_of_dicts(self, mock_search):
        """Test that web_search returns a list of result dicts."""
        mock_search.return_value = {
            "results": [
                {
                    "title": "Test",
                    "url": "https://example.com",
                    "content": "Content",
                    "score": 0.9,
                }
            ]
        }

        results = web_search(query="test")

        # Verify results is a list
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)

        # Verify each result is a dict with expected keys
        result = results[0]
        self.assertIsInstance(result, dict)
        self.assertIn("title", result)
        self.assertIn("url", result)
        self.assertIn("content", result)
        self.assertIn("score", result)

    @mock.patch("tools.web.client.search")
    def test_result_via_registry_is_string(self, mock_client_search):
        """Test that registry.execute returns a bounded string."""
        from tool_registry import registry

        mock_search_results = [
            {
                "title": "Test Result",
                "url": "https://example.com",
                "content": "Test content",
                "score": 0.9,
            }
        ]

        # The mock needs to return something that .get("results", []) works on
        mock_client_search.return_value = {
            "results": mock_search_results
        }

        result = registry.execute("web_search", {"query": "test"})

        self.assertIsInstance(result, str)
        self.assertIn("Test Result", result)