"""
Hermetic registry tests (stdlib unittest, no live services required).

Run from the project root:
    .venv/bin/python -m unittest test_registry -v
"""

import os
import unittest

import audit

from tool_registry import (
    ToolDefinition,
    ToolRegistry,
    bound_output,
    registry,
)

EXPECTED_TOOLS = [
    "docker_ps",
    "docker_images",
    "docker_logs",
    "docker_inspect",
    "prometheus_query",
    "kubernetes_nodes",
    "kubernetes_pods",
    "kubernetes_deployments",
    "kubernetes_services",
    "kubernetes_namespaces",
    "kubernetes_logs",
    "kubernetes_describe",
    "git_status",
    "git_diff",
    "read_file",
    "write_file",
    "web_search",
    "web_fetch",
    "run_command",
]


class TestToolRegistry(unittest.TestCase):

    def setUp(self):
        self._audit_enabled = audit.audit.enabled
        audit.audit.enabled = False

    def tearDown(self):
        audit.audit.enabled = self._audit_enabled

    def test_all_existing_tools_are_registered(self):
        names = registry.names()
        for name in EXPECTED_TOOLS:
            self.assertIn(name, names, f"missing tool: {name}")
        self.assertEqual(
            len(names),
            len(EXPECTED_TOOLS),
            "registry has extra or missing tools",
        )

    def test_get_known_tool(self):
        self.assertIsNotNone(registry.get("prometheus_query"))
        self.assertIsNotNone(registry.get("kubernetes_pods"))
        self.assertEqual(
            registry.get("prometheus_query").name,
            "prometheus_query",
        )

    def test_get_unknown_returns_none(self):
        self.assertIsNone(registry.get("not_a_tool"))

    def test_schemas_are_openai_compatible(self):
        schemas = registry.schemas()
        self.assertEqual(len(schemas), len(EXPECTED_TOOLS))
        for schema in schemas:
            self.assertEqual(schema["type"], "function")
            fn = schema["function"]
            self.assertIn("name", fn)
            self.assertIn("description", fn)
            self.assertIsInstance(fn["description"], str)
            params = fn["parameters"]
            self.assertEqual(params["type"], "object")
            self.assertIsInstance(params.get("properties", {}), dict)

    def test_schemas_cover_all_tool_names(self):
        names = {schema["function"]["name"] for schema in registry.schemas()}
        self.assertEqual(names, set(EXPECTED_TOOLS))

    def test_execute_unknown_tool_is_controlled_error(self):
        result = registry.execute("not_a_tool", {})
        self.assertIsInstance(result, str)
        self.assertIn("Unknown tool", result)

    def test_execute_filters_unexpected_arguments(self):
        result = registry.execute(
            "read_file",
            {"path": "agent.py", "unexpected": 123},
        )
        self.assertIsInstance(result, str)
        self.assertIn("tool_registry", result)

    def test_read_file_is_read_only(self):
        self.assertTrue(registry.get("read_file").read_only)
        self.assertFalse(registry.get("read_file").requires_approval)

    def test_risk_metadata(self):
        self.assertEqual(registry.get("run_command").risk_level, "high")
        self.assertFalse(registry.get("run_command").read_only)
        self.assertEqual(registry.get("write_file").risk_level, "medium")
        self.assertFalse(registry.get("write_file").read_only)
        self.assertEqual(registry.get("prometheus_query").risk_level, "low")
        self.assertTrue(registry.get("prometheus_query").read_only)

    def test_access_level_metadata(self):
        self.assertEqual(registry.get("prometheus_query").access_level, "read")
        self.assertEqual(registry.get("kubernetes_pods").access_level, "read")
        self.assertEqual(registry.get("read_file").access_level, "read")
        self.assertEqual(registry.get("write_file").access_level, "write")
        self.assertEqual(registry.get("run_command").access_level, "write")

    def test_approval_metadata(self):
        self.assertFalse(registry.get("prometheus_query").requires_approval)
        self.assertFalse(registry.get("kubernetes_pods").requires_approval)
        self.assertTrue(registry.get("write_file").requires_approval)
        self.assertTrue(registry.get("run_command").requires_approval)


class TestToolErrorIsolation(unittest.TestCase):

    def setUp(self):
        self._audit_enabled = audit.audit.enabled
        audit.audit.enabled = False

    def tearDown(self):
        audit.audit.enabled = self._audit_enabled

    def _make_registry(self, function, **tool_kwargs):
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="probe",
            description="test tool",
            function=function,
            parameters={"type": "object", "properties": {}},
            read_only=True,
            **tool_kwargs,
        ))
        return reg

    def test_tool_exception_does_not_crash_agent(self):
        def boom(**kwargs):
            raise RuntimeError("kaboom")
        reg = self._make_registry(boom)
        result = reg.execute("probe", {})
        self.assertIsInstance(result, str)
        self.assertIn("Tool execution error", result)

    def test_unknown_tool_does_not_crash_agent(self):
        result = registry.execute("not_a_tool", {})
        self.assertIn("Unknown tool", result)

    def test_large_output_is_bounded_with_marker(self):
        def big(**kwargs):
            return "x" * 20000
        reg = self._make_registry(big)
        result = reg.execute("probe", {})
        self.assertLessEqual(len(result), 8200)
        self.assertIn("OUTPUT TRUNCATED", result)
        self.assertIn("Original output size", result)

    def test_small_output_is_not_truncated(self):
        reg = self._make_registry(lambda **kw: "hello")
        result = reg.execute("probe", {})
        self.assertEqual(result, "hello")

    def test_bound_output_converts_non_strings(self):
        self.assertEqual(bound_output(["a", "b"]), "['a', 'b']")


class TestApprovalBoundary(unittest.TestCase):

    def setUp(self):
        self._original_handler = registry.approval_handler
        self._audit_enabled = audit.audit.enabled
        audit.audit.enabled = False

    def tearDown(self):
        registry.approval_handler = self._original_handler
        audit.audit.enabled = self._audit_enabled

    def _deny_all(self):
        registry.approval_handler = lambda name, args, request_id=None: False

    def test_write_file_denied_without_side_effect(self):
        self._deny_all()
        result = registry.execute(
            "write_file",
            {"path": "nope_test_file.txt", "content": "x"},
        )
        self.assertIn("denied", result.lower())
        self.assertFalse(os.path.exists("nope_test_file.txt"))

    def test_run_command_denied_without_side_effect(self):
        self._deny_all()
        result = registry.execute(
            "run_command",
            {"command": "touch /tmp/opencode_deny_probe"},
        )
        self.assertIn("denied", result.lower())
        self.assertFalse(os.path.exists("/tmp/opencode_deny_probe"))

    def test_approval_granted_executes(self):
        calls = []

        def fake(**kwargs):
            calls.append(kwargs)
            return "done"

        reg = ToolRegistry()
        reg.approval_handler = lambda name, args, request_id=None: True
        reg.register(ToolDefinition(
            name="fake_write",
            description="d",
            function=fake,
            parameters={"type": "object", "properties": {}},
            read_only=False,
            requires_approval=True,
        ))
        result = reg.execute("fake_write", {})
        self.assertEqual(result, "done")
        self.assertEqual(len(calls), 1)

    def test_approval_required_but_no_handler_fails_closed(self):
        reg = ToolRegistry()
        reg.approval_handler = None
        reg.register(ToolDefinition(
            name="fake_write",
            description="d",
            function=lambda **kw: "should not run",
            parameters={"type": "object", "properties": {}},
            read_only=False,
            requires_approval=True,
        ))
        result = reg.execute("fake_write", {})
        self.assertIn("denied", result.lower())


if __name__ == "__main__":
    unittest.main()