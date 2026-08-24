"""
Conversation context management.

Prevents unbounded message growth without a memory database.

Strategy (deterministic and simple):
- the leading system message is always kept
- whole LLM turns are trimmed from the oldest end when the message
  count or approximate character budget is exceeded
- trimming removes a contiguous block starting at a user message and
  ending before the next user message, so tool results are never
  orphaned from their requesting assistant message
"""

import config


def _role(message) -> str | None:
    """Return a message's role whether it is a dict or an API object."""
    if isinstance(message, dict):
        return message.get("role")
    return getattr(message, "role", None)


def _fields(message) -> tuple:
    """Return (content, tool_calls) for dicts and API objects alike."""
    if isinstance(message, dict):
        return message.get("content"), message.get("tool_calls")
    return getattr(message, "content", None), getattr(message, "tool_calls", None)


def _estimate_size(messages: list) -> int:
    """Approximate character size of messages (content + tool calls)."""
    total = 0
    for message in messages:
        content, tool_calls = _fields(message)
        if isinstance(content, str):
            total += len(content)
        elif content is not None:
            total += len(str(content))
        if tool_calls:
            total += len(str(tool_calls))
    return total


def trim_context(
    messages: list,
    max_messages: int | None = None,
    max_chars: int | None = None,
) -> list:
    """Return messages trimmed to stay within configured limits."""
    if max_messages is None:
        max_messages = config.CONTEXT_MAX_MESSAGES
    if max_chars is None:
        max_chars = config.CONTEXT_MAX_CHARS

    if len(messages) <= 1:
        return messages

    pinned: list = []
    body = list(messages)
    if body and _role(body[0]) == "system":
        pinned.append(body.pop(0))

    def over_budget() -> bool:
        return len(body) > max_messages or _estimate_size(body) > max_chars

    while over_budget():
        user_indexes = [i for i, m in enumerate(body) if _role(m) == "user"]
        if len(user_indexes) <= 1:
            break
        first = user_indexes[0]
        second = user_indexes[1]
        del body[first:second]

    return pinned + body