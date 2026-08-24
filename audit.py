"""
Lightweight auditability foundation.

Captures structured events as JSONL (one JSON object per line) for
future audit/review tooling. This is intentionally minimal:

- no secrets, tokens, passwords or full tool outputs are logged
- no stack traces are logged
- a failure to write the audit log must never break the agent
"""

import json
import uuid
from datetime import datetime, timezone

import config

SESSION_ID = uuid.uuid4().hex[:12]


def new_request_id() -> str:
    """Return a fresh request ID for correlation across one turn."""
    return uuid.uuid4().hex[:12]


class AuditLogger:
    """Appends non-sensitive events to a JSONL file."""

    def __init__(self, path: str | None = None, enabled: bool | None = None):
        self.path = path if path is not None else config.AUDIT_LOG_PATH
        self.enabled = enabled if enabled is not None else config.AUDIT_ENABLED

    def record(self, **fields) -> None:
        if not self.enabled:
            return
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session": SESSION_ID,
            **fields,
        }
        try:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


audit = AuditLogger()


def record(**fields) -> None:
    """Module-level convenience delegate for audit.record(...)."""
    audit.record(**fields)