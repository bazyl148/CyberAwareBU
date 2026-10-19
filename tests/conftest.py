"""Test setup: run against a real AIGoat checkout with the overlay installed.

    scripts/install-overlay.sh /path/to/AIGoat
    AIGOAT_DIR=/path/to/AIGoat python -m pytest tests/

Only light dependencies are needed (pytest, pyyaml, pydantic, fastapi,
sqlalchemy[asyncio], aiosqlite, httpx, python-jose, passlib); no Ollama,
Chroma or embedding model.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

AIGOAT_DIR = Path(os.environ.get("AIGOAT_DIR", Path.home() / "AIGoat")).expanduser()
PROFILE = AIGOAT_DIR / "config" / "cyberaware_profiles.yml"

if not (AIGOAT_DIR / "app" / "defense" / "controls" / "cyberaware").is_dir():
    pytest.exit(
        f"No AIGoat checkout with the overlay at {AIGOAT_DIR}. "
        "Run scripts/install-overlay.sh first and set AIGOAT_DIR.",
        returncode=4,
    )

sys.path.insert(0, str(AIGOAT_DIR))
# Must be set before AIGoat loads (and caches) its profiles.
os.environ["DEFENSE_PROFILES_PATH"] = str(PROFILE)


@pytest.fixture(autouse=True)
def audit_log(tmp_path, monkeypatch):
    """Send audit records to a per-test file instead of AIGoat's logs/."""
    path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("CYBERAWARE_AUDIT_LOG", str(path))
    return path


def chunk(content: str, *, injected: bool, tier: str, owner_id=None, entry_id=1) -> dict:
    """A retrieval hit shaped like app/rag/retrieval.py query() output."""
    return {
        "content": content,
        "metadata": {"entry_id": entry_id, "title": f"entry {entry_id}"},
        "distance": 0.1,
        "id": f"chunk-{entry_id}",
        "is_user_injected": injected,
        "trust_tier": tier,
        "owner_id": owner_id,
    }
