"""
Structured logging for LEO (spec: logging section).

Every pipeline stage (INTENT / PLAN / ACTION / OBSERVATION / VERIFICATION /
RESPONSE) is logged in a consistent structured form to logs/leo.log and to
the console. Secrets (API keys, tokens, passwords) are redacted before
anything is written.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings

_SECRET_PATTERNS = [
    re.compile(r"(\"?[\w-]*api[_-]?key\"?\s*[:=]\s*\"?)([^\s,'\"}]+)", re.IGNORECASE),
    re.compile(r"(\"?authorization\"?\s*[:=]\s*\"?)([^\s,'\"}]+)", re.IGNORECASE),
    re.compile(r"(\"?[\w-]*password\"?\s*[:=]\s*\"?)([^\s,'\"}]+)", re.IGNORECASE),
    re.compile(r"(\"?[\w-]*token\"?\s*[:=]\s*\"?)([^\s,'\"}]+)", re.IGNORECASE),
]


def redact(text: str) -> str:
    """Best-effort redaction of secrets before they hit any log sink."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: f"{m.group(1)}***REDACTED***", redacted)
    return redacted


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("leo")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:
        return logger  # already configured (e.g. re-imported)

    log_path = Path(settings.log_dir) / "leo.log"

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


_logger = _build_logger()


def log_stage(stage: str, payload: dict[str, Any], to_console: bool = True) -> None:
    """
    Log one pipeline stage in structured form:

    {"time": ..., "stage": ..., ...payload}
    """
    safe_payload = json.loads(redact(json.dumps(payload, default=str)))
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": stage,
        **safe_payload,
    }
    line = json.dumps(record, ensure_ascii=False)
    try:
        from app.core import events

        events.on_stage(stage, safe_payload)
    except Exception:  # noqa: BLE001 - UI state must never break logging
        pass
    if to_console:
        _logger.info(line)
    else:
        _logger.debug(line)


def get_logger() -> logging.Logger:
    return _logger
