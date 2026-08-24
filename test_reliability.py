"""
Reliability tests: LLM error handling, context management, subprocess
timeouts. No live services (Prometheus, Kubernetes, Docker) are required.

Run from the project root:
    .venv/bin/python -m unittest test_reliability -v
"""

import subprocess
import unittest
from unittest import mock

import openai
import requests

import audit
import config
import context
import llm
from tools import prometheus, shell, subprocess_utils


def _disable_audit(testcase):
    testcase._audit_enabled = audit.audit.enabled
    audit.audit.enabled = False


def _restore_audit(testcase):
    audit.audit.enabled = testcase._audit_enabled


class _FakeMessage:
    def __init__(self, content="ok", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


class _EmptyResponse:
    choices = []


def _api_timeout():
    import httpx
    request = httpx.Request("POST", "http://localhost:1/v1/chat/completions")
    return openai.APITimeoutError(request=request)


def _api_connection_error():
    import httpx
    request = httpx.Request("POST", "http://localhost:1/v1/chat/completions")
    return openai.APIConnectionError(request=request)


def _api_status_error(status_code=500):
    import httpx
    request = httpx.Request("POST", "http://localhost:1/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return openai.APIStatusError(
        message="server error",
        response=response,
        body=None,
    )


class TestLLMErrorHandling(unittest.TestCase):

    def setUp(self):
        _disable_audit(self)
        self.messages = [{"role": "user", "content": "hello"}]

    def tearDown(self):
        _restore_audit(self)

    def _call(self, side_effect):
        with mock.patch.object(
            llm.client.chat.completions, "create", side_effect=side_effect
        ):
            return llm.call_llm(self.messages)

    def test_timeout_is_handled(self):
        message, error = self._call(_api_timeout())
        self.assertIsNone(message)
        self.assertIn("timed out", error)

    def test_connection_failure_is_handled(self):
        message, error = self._call(_api_connection_error())
        self.assertIsNone(message)
        self.assertIn("Ollama", error)

    def test_http_error_is_handled(self):
        message, error = self._call(_api_status_error(500))
        self.assertIsNone(message)
        self.assertIn("HTTP 500", error)

    def test_unexpected_exception_is_handled(self):
        message, error = self._call(RuntimeError("boom"))
        self.assertIsNone(message)
        self.assertIn("unexpected", error.lower())

    def test_empty_response_is_handled(self):
        with mock.patch.object(
            llm.client.chat.completions,
            "create",
            return_value=_EmptyResponse(),
        ):
            message, error = llm.call_llm(self.messages)
        self.assertIsNone(message)
        self.assertIn("empty response", error)

    def test_success_returns_message(self):
        response = _FakeResponse(_FakeMessage(content="hello back"))
        with mock.patch.object(
            llm.client.chat.completions,
            "create",
            return_value=response,
        ):
            message, error = llm.call_llm(self.messages)
        self.assertIsNone(error)
        self.assertEqual(message.content, "hello back")

    def test_retry_then_success(self):
        response = _FakeResponse(_FakeMessage(content="recovered"))
        with mock.patch.object(
            llm.client.chat.completions, "create",
            side_effect=[_api_timeout(), response],
        ), mock.patch.object(config, "LLM_MAX_RETRIES", 1), \
           mock.patch.object(llm.time, "sleep", return_value=None):
            message, error = llm.call_llm(self.messages)
        self.assertIsNone(error)
        self.assertEqual(message.content, "recovered")


class TestContextManagement(unittest.TestCase):

    def test_trim_by_message_count(self):
        messages = [{"role": "system", "content": "S"}]
        messages += [
            {"role": m, "content": c}
            for turn in range(10)
            for m, c in (("user", f"u{turn}"), ("assistant", f"a{turn}"))
        ]
        trimmed = context.trim_context(messages, max_messages=6, max_chars=10**9)
        self.assertEqual(trimmed[0]["role"], "system")
        self.assertLessEqual(len(trimmed) - 1, 6)
        self.assertEqual(trimmed[1]["role"], "user")

    def test_trim_by_char_budget(self):
        messages = [{"role": "system", "content": "S"}]
        messages += [{"role": "user", "content": "x" * 1000}]
        messages += [{"role": "assistant", "content": "y" * 1000}]
        messages += [{"role": "user", "content": "z" * 1000}]
        trimmed = context.trim_context(messages, max_messages=100, max_chars=1500)
        self.assertEqual(trimmed[0]["role"], "system")
        self.assertLessEqual(trimmed[-1]["content"], "z" * 1000)

    def test_tool_messages_are_never_orphaned(self):
        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "1", "function": {"name": "x"}}]},
            {"role": "tool", "tool_call_id": "1", "content": "r1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
            {"role": "assistant", "content": "a3"},
        ]
        trimmed = context.trim_context(messages, max_messages=4, max_chars=10**9)
        self.assertEqual(trimmed[0]["role"], "system")
        for i, m in enumerate(trimmed):
            if m.get("role") == "tool":
                self.assertGreater(i, 0)
                prev = trimmed[i - 1]
                self.assertIn("tool_calls", prev)

    def test_single_turn_is_preserved(self):
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}]
        trimmed = context.trim_context(messages, max_messages=1, max_chars=1)
        self.assertEqual(len(trimmed), 2)

    def test_handles_api_message_objects(self):
        class Obj:
            def __init__(self, role, content, tool_calls=None):
                self.role = role
                self.content = content
                self.tool_calls = tool_calls

        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "u1"},
            Obj("assistant", None, [{"id": "1", "function": {"name": "x"}}]),
            {"role": "tool", "tool_call_id": "1", "content": "r1"},
            Obj("assistant", "a1"),
            {"role": "user", "content": "u2"},
            Obj("assistant", "a2"),
            {"role": "user", "content": "u3"},
            Obj("assistant", "a3"),
        ]
        trimmed = context.trim_context(messages, max_messages=4, max_chars=10**9)
        self.assertEqual(trimmed[0]["role"], "system")
        for i, m in enumerate(trimmed):
            role = m.get("role") if isinstance(m, dict) else m.role
            if role == "tool":
                self.assertGreater(i, 0)
                self.assertIn("tool_calls", trimmed[i - 1])


class TestSubprocessTimeout(unittest.TestCase):

    def test_run_bounded_timeout_returns_controlled_error(self):
        with mock.patch.object(
            subprocess_utils.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="kubectl get nodes", timeout=30),
        ):
            result = subprocess_utils.run_bounded(
                ["kubectl", "get", "nodes"],
                timeout=30,
                error_label="Kubernetes",
            )
        self.assertIn("timed out", result)
        self.assertIn("Kubernetes", result)

    def test_run_bounded_missing_executable(self):
        with mock.patch.object(
            subprocess_utils.subprocess,
            "run",
            side_effect=FileNotFoundError(),
        ):
            result = subprocess_utils.run_bounded(["docker", "ps"], error_label="Docker")
        self.assertIn("not found", result)
        self.assertIn("docker", result)

    def test_run_bounded_success(self):
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n")
        with mock.patch.object(
            subprocess_utils.subprocess, "run", return_value=fake
        ):
            result = subprocess_utils.run_bounded(["echo", "ok"])
        self.assertEqual(result, "ok\n")

    def test_run_bounded_nonzero_exit(self):
        fake = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="boom"
        )
        with mock.patch.object(
            subprocess_utils.subprocess, "run", return_value=fake
        ):
            result = subprocess_utils.run_bounded(
                ["git", "status"], error_label="Git"
            )
        self.assertIn("Git error", result)
        self.assertIn("boom", result)

    def test_shell_command_timeout(self):
        with mock.patch.object(
            shell.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="sleep 999", timeout=60),
        ):
            result = shell.run_command("sleep 999")
        self.assertIn("timed out", result)

    def test_shell_command_success(self):
        fake = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="hello", stderr=""
        )
        with mock.patch.object(shell.subprocess, "run", return_value=fake):
            result = shell.run_command("echo hello")
        self.assertIn("hello", result)
        self.assertIn("Exit code: 0", result)


class TestPrometheusErrorHandling(unittest.TestCase):

    def test_prometheus_query_success(self):
        fake = mock.Mock()
        fake.raise_for_status = lambda: None
        fake.json.return_value = {
            "status": "success",
            "data": {"result": [{"metric": {"__name__": "up"}, "value": [1, "1"]}]},
        }
        with mock.patch("tools.prometheus.requests.get", return_value=fake) as m:
            result = prometheus.prometheus_query("up")
        m.assert_called_once()
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["metric"]["__name__"], "up")

    def test_prometheus_query_connection_error(self):
        with mock.patch(
            "tools.prometheus.requests.get",
            side_effect=requests.ConnectionError("connection refused"),
        ):
            result = prometheus.prometheus_query("up")
        self.assertIn("Prometheus connection error", result)

    def test_prometheus_query_http_error(self):
        fake = mock.Mock()
        fake.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        with mock.patch("tools.prometheus.requests.get", return_value=fake):
            result = prometheus.prometheus_query("up")
        self.assertIn("Prometheus connection error", result)

    def test_prometheus_query_non_success_status(self):
        fake = mock.Mock()
        fake.raise_for_status = lambda: None
        fake.json.return_value = {"status": "error", "error": "bad query"}
        with mock.patch("tools.prometheus.requests.get", return_value=fake):
            result = prometheus.prometheus_query("up")
        self.assertIn("Prometheus error", result)


if __name__ == "__main__":
    unittest.main()