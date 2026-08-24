"""
LLM integration with bounded timeouts and graceful failure handling.

A failed or slow LLM request must never crash the agent. Every error
is mapped to a clear, user-facing message; no stack traces and no
secrets are surfaced.
"""

import time

import openai

import audit
import config
from tool_registry import registry

MODEL = config.LLM_MODEL

client = openai.OpenAI(
    base_url=config.OLLAMA_BASE_URL,
    api_key="ollama",
)


def _friendly_error(exc: Exception) -> tuple[str, bool]:
    """Map an exception to (friendly message, retryable)."""
    if isinstance(exc, openai.APITimeoutError):
        return (
            f"The language model request timed out after "
            f"{config.LLM_TIMEOUT_SECONDS} seconds.",
            True,
        )
    if isinstance(exc, openai.APIConnectionError):
        return (
            "Could not reach the local language model (Ollama). "
            "Make sure Ollama is running.",
            True,
        )
    if isinstance(exc, openai.RateLimitError):
        return (
            "The language model is busy (rate limited). "
            "Please try again shortly.",
            True,
        )
    if isinstance(exc, openai.AuthenticationError):
        return (
            "The language model rejected the API key.",
            False,
        )
    if isinstance(exc, openai.BadRequestError):
        return (
            "The request was rejected by the language model "
            "(invalid request).",
            False,
        )
    if isinstance(exc, openai.APIStatusError):
        return (
            f"The language model returned an error "
            f"(HTTP {getattr(exc, 'status_code', 'unknown')}).",
            True,
        )
    if isinstance(exc, openai.APIError):
        return (
            "The language model API reported an error.",
            False,
        )
    return (
        "An unexpected error occurred while contacting the language model.",
        False,
    )


def call_llm(messages: list[dict], request_id: str | None = None):
    """Call the LLM once, with retries and controlled error handling.

    Returns (message, None) on success, or (None, error_text) on
    failure. message is an OpenAI chat message object (with optional
    tool_calls) ready to be appended to the conversation.
    """
    attempt = 0

    while True:
        attempt += 1
        started = time.time()

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=registry.schemas(),
                timeout=config.LLM_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - deliberate isolation
            message, retryable = _friendly_error(exc)
            audit.record(
                event="llm_error",
                request_id=request_id,
                attempt=attempt,
                error=message,
            )
            if retryable and attempt <= config.LLM_MAX_RETRIES:
                time.sleep(1)
                continue
            return None, message

        if not response.choices:
            audit.record(
                event="llm_error",
                request_id=request_id,
                attempt=attempt,
                error="empty response",
            )
            return None, "The language model returned an empty response."

        message = response.choices[0].message

        audit.record(
            event="llm_response",
            request_id=request_id,
            attempt=attempt,
            duration_ms=int((time.time() - started) * 1000),
            tool_calls=bool(message.tool_calls),
        )

        return message, None