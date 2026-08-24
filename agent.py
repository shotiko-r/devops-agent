import json
import sys

import audit
import config
import context as context_manager
from llm import call_llm
from tool_registry import registry


# -- Terminal colour support (graceful fallback) ---------------

USE_COLOR = sys.stdout.isatty()

RESET = "\033[0m"
CYAN = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"


def cyan(text: str) -> str:
    if USE_COLOR:
        return f"{CYAN}{text}{RESET}"
    return text


def green(text: str) -> str:
    if USE_COLOR:
        return f"{GREEN}{text}{RESET}"
    return text


def yellow(text: str) -> str:
    if USE_COLOR:
        return f"{YELLOW}{text}{RESET}"
    return text


# --------------------------------------------------------------


# ============================================================
# TOOL DEFINITIONS
# ============================================================
#
# Tool schemas, functions and metadata are defined in
# tool_registry.py. The model receives registry.schemas() and
# tool calls are executed through registry.execute(). Approval of
# dangerous tools is enforced by the registry boundary, not the model.


# ============================================================
# TOOL EXECUTOR
# ============================================================

def execute_tool(name, arguments, request_id=None):
    """Backward-compatible wrapper delegating to the registry."""
    return registry.execute(name, arguments, request_id=request_id)


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """

You are a local DevOps AI agent.

You run locally on the user's computer using Ollama
and a local Qwen model.

LANGUAGE:

- Understand Georgian and English.
- If the user writes in Georgian, respond in clear natural Georgian.
- If the user writes in English, respond in English.
- Keep commands, code, filenames, API names and technical
  identifiers in English.
- Explain technical concepts in Georgian when appropriate.


AVAILABLE TOOLS:

Docker:
- running containers
- Docker images
- container logs
- container inspection

Kubernetes:
- nodes
- pods
- deployments
- services
- namespaces
- pod logs
- resource descriptions

Prometheus:
- PromQL queries
- monitoring metrics
- target health
- CPU and memory metrics
- Kubernetes metrics
- pod/container metrics

Git:
- git status
- git diff

Files:
- read files
- write files with approval

Web:
- internet search
- current information
- recent news
- research sources

Shell:
- execute commands with approval


IMPORTANT RULES:

1. Inspect before modifying.

2. Read unfamiliar files before changing them.

3. Never claim that a tool was executed unless it actually was.

4. Never invent command output.

5. Use tools when real system information is required.

6. If the user asks about Docker, Kubernetes, Git,
   Prometheus or files, use the appropriate tool instead of guessing.

7. If a task requires multiple tools, use them sequentially.

8. File modifications require explicit user approval.

9. Shell command execution requires explicit user approval.

10. Do not modify unrelated files.

11. Keep changes minimal and focused.

12. When reporting system information, distinguish real tool
    output from your own interpretation.


KUBERNETES:

When the user asks about Kubernetes pods, use kubernetes_pods.

When the user asks about Kubernetes nodes, use kubernetes_nodes.

When the user asks about deployments, use kubernetes_deployments.

When the user asks about services, use kubernetes_services.

When the user asks about namespaces, use kubernetes_namespaces.

When the user asks for pod logs, use kubernetes_logs.

When the user asks for detailed Kubernetes resource information,
use kubernetes_describe.

Do not tell the user that a Kubernetes tool is unavailable
if the corresponding tool is present in the tool list.


PROMETHEUS:

When the user asks about monitoring, metrics, CPU, memory,
resource usage, target health, Prometheus data, or whether
monitoring targets are up/down, use prometheus_query.

When checking monitoring target health, prefer PromQL such as:

up

or:

up == 0

Do not infer Prometheus target health from Kubernetes pod status.

A Kubernetes pod being Running does not necessarily mean that
its Prometheus monitoring target is up.

Always use real Prometheus data before making claims about
monitoring health.

Do not invent metric values.

You are a DevOps and coding assistant.

"""


# ============================================================
# AGENT LOOP
# ============================================================

def run_agent():

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    while True:

        command = input(f"\n{cyan('You: ')}")

        if command.lower() in ["exit", "quit"]:
            print("Agent stopped.")
            break

        messages.append(
            {
                "role": "user",
                "content": command,
            }
        )

        request_id = audit.new_request_id()

        iterations = 0
        max_iterations = config.MAX_TOOL_ITERATIONS

        while True:

            iterations += 1
            if iterations > max_iterations:
                print(
                    f"\n{yellow('🔧 Maximum tool iterations reached')} ({max_iterations}). "
                    f"Stopping tool execution.{RESET}"
                )
                audit.record(
                    event="max_iterations_reached",
                    request_id=request_id,
                    iterations=max_iterations,
                )
                # Preserve conversation state by not clearing messages
                break

            messages = context_manager.trim_context(messages)

            message, error = call_llm(messages, request_id=request_id)

            if error:
                print(f"\n{green('Agent:')}", error)
                break

            messages.append(message)

            if not message.tool_calls:
                print(f"\n{green('Agent:')}", message.content)
                break

            # ------------------------------------------------
            # Execute requested tools
            # ------------------------------------------------

            for tool_call in message.tool_calls:

                name = tool_call.function.name

                try:
                    raw_arguments = tool_call.function.arguments
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    # Unparseable JSON — treat as missing arguments
                    arguments = {}
                    print(
                        f"\n{yellow('🔧 Tool:')} {name} — "
                        f"could not parse tool call arguments; "
                        f"using empty arguments.{RESET}"
                    )

                # Validate that required arguments are present.
                # Each tool's required parameters are defined in the registry.
                try:
                    tool = registry.get(name)
                except Exception:
                    print(
                        f"\n{yellow('🔧 Tool:')} {name} — unknown tool, skipping.{RESET}"
                    )
                    continue

                if tool is None:
                    print(
                        f"\n{yellow('🔧 Tool:')} {name} — unknown tool, skipping.{RESET}"
                    )
                    continue

                properties = tool.parameters.get("properties", {})
                required = tool.parameters.get("required", [])
                missing = [arg for arg in required if arg not in arguments]
                if missing:
                    print(
                        f"\n{yellow('🔧 Tool:')} {name} — missing required argument(s): "
                        f"{', '.join(missing)}; skipping.{RESET}"
                    )
                    continue

                print(f"\n{yellow('🔧 Tool:')} {name}")

                result = execute_tool(
                    name,
                    arguments,
                    request_id=request_id,
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(result),
                    }
                )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    print("========================================")
    print("       LOCAL DEVOPS AI AGENT")
    print("========================================")
    print(f"Model: {config.LLM_MODEL}")
    print("Language: Georgian / English")
    print("Docker: enabled")
    print("Kubernetes: enabled")
    print("Prometheus: enabled")
    print("Git: enabled")
    print("Files: enabled")
    print("Shell: enabled")
    print("Web: enabled")
    print(f"Session: {audit.SESSION_ID}")
    print("Type '/' for commands later.")
    print("Type 'exit' to quit.")
    print()

    run_agent()