"""Append-only JSONL audit log for CyberAware control decisions.

One line per decision a control makes, so every block can be shown on stage
(``tools/audit_tail.py``) and counted by the evaluation harness. Writes are
fail-safe: an audit failure is logged and never breaks the request path,
matching AIGoat's own ``app/defense/telemetry.py``.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


def _default_path() -> Path:
    # Installed at <AIGoat>/app/defense/controls/cyberaware/audit.py
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "logs" / "cyberaware-audit.jsonl"


def audit_path() -> Path:
    override = os.environ.get("CYBERAWARE_AUDIT_LOG")
    return Path(override) if override else _default_path()


def record(
    *,
    control_id: str,
    surface: str,
    stage: str,
    level: int,
    action: str,
    reason: str | None,
    user_id: int | None = None,
    elapsed_ms: float | None = None,
    **details: Any,
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "control": control_id,
        "surface": surface,
        "stage": stage,
        "level": level,
        "action": action,
        "reason": reason,
        "user_id": user_id,
        "elapsed_ms": round(elapsed_ms, 3) if elapsed_ms is not None else None,
        **details,
    }
    try:
        path = audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, default=str)
        with _LOCK, path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:  # never block the request path
        logger.warning("CyberAware audit write failed (non-blocking): %s", exc)
