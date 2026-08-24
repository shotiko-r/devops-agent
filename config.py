"""
Central configuration, loaded from environment variables.

Every tunable value lives here. Values can be overridden through
.env (or the process environment). See the individual defaults.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    """Read an integer environment variable with a safe default."""
    try:
        value = os.getenv(name)
        if value is None or value.strip() == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------
# LLM / Ollama
# ------------------------------------------------------------------

LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:14b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
LLM_TIMEOUT_SECONDS = _int_env("LLM_TIMEOUT_SECONDS", 120)
LLM_MAX_RETRIES = _int_env("LLM_MAX_RETRIES", 1)

# ------------------------------------------------------------------
# Prometheus
# ------------------------------------------------------------------

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
PROMETHEUS_TIMEOUT_SECONDS = _int_env("PROMETHEUS_TIMEOUT_SECONDS", 10)

# ------------------------------------------------------------------
# Subprocess timeouts (seconds)
# ------------------------------------------------------------------
# SUBCOMMAND_TIMEOUT_SECONDS is the generic default. Domain-specific
# values fall back to it unless overridden individually.

SUBCOMMAND_TIMEOUT_SECONDS = _int_env("SUBCOMMAND_TIMEOUT_SECONDS", 30)
KUBERNETES_TIMEOUT_SECONDS = _int_env(
    "KUBERNETES_TIMEOUT_SECONDS", SUBCOMMAND_TIMEOUT_SECONDS
)
DOCKER_TIMEOUT_SECONDS = _int_env(
    "DOCKER_TIMEOUT_SECONDS", SUBCOMMAND_TIMEOUT_SECONDS
)
GIT_TIMEOUT_SECONDS = _int_env("GIT_TIMEOUT_SECONDS", SUBCOMMAND_TIMEOUT_SECONDS)
SHELL_COMMAND_TIMEOUT_SECONDS = _int_env("SHELL_COMMAND_TIMEOUT_SECONDS", 60)

# ------------------------------------------------------------------
# Conversation context management
# ------------------------------------------------------------------

CONTEXT_MAX_MESSAGES = _int_env("CONTEXT_MAX_MESSAGES", 24)
CONTEXT_MAX_CHARS = _int_env("CONTEXT_MAX_CHARS", 120000)

# ------------------------------------------------------------------
# Tool output protection
# ------------------------------------------------------------------

MAX_TOOL_RESULT_CHARS = _int_env("MAX_TOOL_RESULT_CHARS", 8000)

# ------------------------------------------------------------------
# Tool iteration safety
# ------------------------------------------------------------------

MAX_TOOL_ITERATIONS = _int_env("MAX_TOOL_ITERATIONS", 8)

# ------------------------------------------------------------------
# Auditability
# ------------------------------------------------------------------

AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "audit.log")
AUDIT_ENABLED = _bool_env("AUDIT_ENABLED", True)