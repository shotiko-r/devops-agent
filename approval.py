"""
Human approval boundary.

The approval decision is enforced by the application (ToolRegistry),
never by the LLM. Tools declare requires_approval and the registry
calls this handler before executing them. The model cannot bypass it
by emitting another tool call: every execution of an approval-gated
tool passes through the handler again.
"""

import sys

USE_COLOR = sys.stdout.isatty()

RESET = "\033[0m"
CYAN = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"


def _c(text: str) -> str:
    """Return *text* wrapped in ANSI colour codes when colours are enabled."""
    if USE_COLOR:
        return f"{text}{RESET}"
    return text


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


import audit


def prompt_approval(name: str, arguments: dict, request_id: str | None = None) -> bool:
    """Ask the user to approve a risky tool call. Returns True if allowed."""
    print()
    print(yellow("⚠️ ACTION REQUIRES APPROVAL"))
    print(f"Tool: {name}")
    for key, value in arguments.items():
        print(f"  {key}: {value}")
    print()

    answer = input("Approve this action? [y/N]: ")
    approved = answer.strip().lower() == "y"

    audit.record(
        event="approval",
        request_id=request_id,
        tool=name,
        approved=approved,
    )

    return approved