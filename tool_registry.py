"""
Centralized Tool Registry.

Single source of truth for every tool exposed to the LLM:
- name
- description
- Python function
- OpenAI/Ollama JSON schema
- risk metadata (read_only, risk_level)

The agent discovers tools through registry.schemas() and executes
them through registry.execute().
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import audit
import config
from approval import prompt_approval

from tools.docker import (
    docker_ps,
    docker_images,
    docker_logs,
    docker_inspect,
)

from tools.kubernetes import (
    kubernetes_nodes,
    kubernetes_pods,
    kubernetes_deployments,
    kubernetes_services,
    kubernetes_namespaces,
    kubernetes_logs,
    kubernetes_describe,
)

from tools.prometheus import prometheus_query

from tools.git import (
    git_status,
    git_diff,
)

from tools.files import (
    read_file,
    write_file,
)

from tools.shell import (
    run_command,
)

from tools.web import web_search, web_fetch


RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

# Conceptual access levels (used by future policy/approval logic).
ACCESS_READ = "read"
ACCESS_DRAFT = "draft"
ACCESS_WRITE = "write"
ACCESS_EXTERNAL_ACTION = "external_action"


def bound_output(value, max_chars: int | None = None) -> str:
    """Return a tool result as a bounded string.

    Large results are truncated with an explicit marker so the LLM
    always knows the output was cut, and how large it originally was.
    """
    if max_chars is None:
        max_chars = config.MAX_TOOL_RESULT_CHARS

    text = value if isinstance(value, str) else str(value)

    if len(text) <= max_chars:
        return text

    note = (
        f"\n\n[OUTPUT TRUNCATED] Original output size: {len(text)} "
        f"characters (limit: {max_chars}). "
        f"Consider asking for more specific data."
    )

    return text[:max_chars] + note


@dataclass(frozen=True)
class ToolDefinition:
    """Metadata + callable for one tool."""

    name: str
    description: str
    function: Callable
    parameters: dict[str, Any]
    read_only: bool
    risk_level: str = RISK_LOW
    access_level: str = ACCESS_READ
    requires_approval: bool = False

    def schema(self) -> dict[str, Any]:
        """OpenAI/Ollama compatible function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registers tools and resolves schemas and execution."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self.approval_handler: Callable | None = prompt_approval

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        request_id: str | None = None,
    ) -> str:
        """Resolve and run a tool, returning a bounded string result.

        The approval boundary is enforced here, outside the model's
        reasoning. A single tool failure is isolated to a controlled
        error string; the agent never crashes because of one tool.
        """
        tool = self.get(name)

        if tool is None:
            audit.record(
                event="tool_unknown",
                request_id=request_id,
                tool=name,
            )
            return f"Unknown tool: {name}"

        allowed = set(tool.parameters.get("properties", {}).keys())
        kwargs = {
            key: value
            for key, value in arguments.items()
            if key in allowed
        }

        approval = "not_required"
        if tool.requires_approval:
            handler = self.approval_handler
            if handler is None:
                audit.record(
                    event="tool_denied",
                    request_id=request_id,
                    tool=name,
                    reason="no approval handler configured",
                )
                return (
                    f"Action denied: no approval handler configured "
                    f"for {name}."
                )
            approved = handler(name, arguments, request_id=request_id)
            approval = "approved" if approved else "denied"
            if not approved:
                audit.record(
                    event="tool_denied",
                    request_id=request_id,
                    tool=name,
                    risk_level=tool.risk_level,
                )
                return f"Action denied: user did not approve {name}."

        started = time.time()
        try:
            result = tool.function(**kwargs)
        except Exception as exc:  # noqa: BLE001 - deliberate isolation
            error = f"{type(exc).__name__}: {exc}"
            audit.record(
                event="tool_error",
                request_id=request_id,
                tool=name,
                risk_level=tool.risk_level,
                error=error,
                duration_ms=int((time.time() - started) * 1000),
            )
            return f"Tool execution error: {error}"

        bounded = bound_output(result)

        audit.record(
            event="tool_executed",
            request_id=request_id,
            tool=name,
            risk_level=tool.risk_level,
            access_level=tool.access_level,
            approval=approval,
            duration_ms=int((time.time() - started) * 1000),
        )

        return bounded


# ============================================================
# REGISTERED TOOLS
# ============================================================

registry = ToolRegistry()

registry.register(ToolDefinition(
    name="docker_ps",
    description="Show currently running Docker containers.",
    function=docker_ps,
    parameters={"type": "object", "properties": {}},
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="docker_images",
    description="Show Docker images available locally.",
    function=docker_images,
    parameters={"type": "object", "properties": {}},
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="docker_logs",
    description="Show recent logs from a Docker container.",
    function=docker_logs,
    parameters={
        "type": "object",
        "properties": {
            "container": {
                "type": "string",
                "description": "Docker container name or ID.",
            },
            "tail": {
                "type": "integer",
                "description": "Number of recent log lines.",
            },
        },
        "required": ["container"],
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="docker_inspect",
    description="Inspect a Docker container.",
    function=docker_inspect,
    parameters={
        "type": "object",
        "properties": {
            "container": {
                "type": "string",
                "description": "Docker container name or ID.",
            },
        },
        "required": ["container"],
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="prometheus_query",
    description=(
        "Execute a PromQL query against the local Prometheus "
        "server and return real monitoring metrics. "
        "Use this for monitoring, CPU, memory, target health, "
        "Kubernetes metrics, pod restarts, and resource usage."
    ),
    function=prometheus_query,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A valid PromQL query.",
            },
        },
        "required": ["query"],
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="kubernetes_nodes",
    description="Show Kubernetes cluster nodes and their status.",
    function=kubernetes_nodes,
    parameters={"type": "object", "properties": {}},
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="kubernetes_pods",
    description="Show Kubernetes pods. Optionally filter by namespace.",
    function=kubernetes_pods,
    parameters={
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": "Optional Kubernetes namespace.",
            },
        },
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="kubernetes_deployments",
    description="Show Kubernetes deployments. Optionally filter by namespace.",
    function=kubernetes_deployments,
    parameters={
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": "Optional Kubernetes namespace.",
            },
        },
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="kubernetes_services",
    description="Show Kubernetes services. Optionally filter by namespace.",
    function=kubernetes_services,
    parameters={
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": "Optional Kubernetes namespace.",
            },
        },
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="kubernetes_namespaces",
    description="Show all Kubernetes namespaces.",
    function=kubernetes_namespaces,
    parameters={"type": "object", "properties": {}},
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="kubernetes_logs",
    description="Show logs from a Kubernetes pod.",
    function=kubernetes_logs,
    parameters={
        "type": "object",
        "properties": {
            "pod": {
                "type": "string",
                "description": "Kubernetes pod name.",
            },
            "namespace": {
                "type": "string",
                "description": "Optional Kubernetes namespace.",
            },
        },
        "required": ["pod"],
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="kubernetes_describe",
    description=(
        "Describe a Kubernetes resource such as pod, "
        "deployment, service or node."
    ),
    function=kubernetes_describe,
    parameters={
        "type": "object",
        "properties": {
            "resource": {
                "type": "string",
                "description": (
                    "Resource type such as pod, deployment, "
                    "service or node."
                ),
            },
            "name": {
                "type": "string",
                "description": "Resource name.",
            },
            "namespace": {
                "type": "string",
                "description": "Optional Kubernetes namespace.",
            },
        },
        "required": ["resource", "name"],
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="git_status",
    description="Show Git branch and working tree status.",
    function=git_status,
    parameters={"type": "object", "properties": {}},
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="git_diff",
    description="Show the current uncommitted Git diff.",
    function=git_diff,
    parameters={"type": "object", "properties": {}},
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="read_file",
    description="Read a text file inside the current project.",
    function=read_file,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the project root.",
            },
        },
        "required": ["path"],
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="write_file",
    description=(
        "Write a text file inside the project. "
        "Requires user approval."
    ),
    function=write_file,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the project root.",
            },
            "content": {
                "type": "string",
                "description": "Complete file content.",
            },
        },
        "required": ["path", "content"],
    },
    read_only=False,
    risk_level=RISK_MEDIUM,
    access_level=ACCESS_WRITE,
    requires_approval=True,
))

registry.register(ToolDefinition(
    name="web_search",
    description=(
        "Search the internet for current information. "
        "Use this when the user asks for recent news, "
        "current information, research, sources, or topics "
        "that may have changed over time."
    ),
    function=web_search,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The web search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of search results.",
            },
        },
        "required": ["query"],
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="web_fetch",
    description=(
        "Fetch a webpage and return readable extracted content. "
        "Use this when the user needs to see the actual source "
        "content from a URL, after an initial web search."
    ),
    function=web_fetch,
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch. Only https:// URLs from public, routable hosts are allowed.",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum number of extracted characters to return (default 3000).",
            },
        },
        "required": ["url"],
    },
    read_only=True,
    risk_level=RISK_LOW,
))

registry.register(ToolDefinition(
    name="run_command",
    description=(
        "Run a shell command inside the project. "
        "Requires user approval."
    ),
    function=run_command,
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute.",
            },
        },
        "required": ["command"],
    },
    read_only=False,
    risk_level=RISK_HIGH,
    access_level=ACCESS_WRITE,
    requires_approval=True,
))