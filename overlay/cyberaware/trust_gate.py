"""cyberaware.trust_gate: keep untrusted knowledge-base content out of the prompt.

Stock ``retrieval.provenance`` only annotates ``trust_tier``; nothing excludes
untrusted chunks, so user-planted "policies" reach the model as fact (CTF 7).
This control excludes a chunk when the server marked it ``is_user_injected``
or its ``trust_tier`` is not allowlisted.

``is_user_injected`` is checked first because the server always sets it for
entries created through the API, while ``trust_tier`` is client-supplied in
stock AIGoat (see patches/0003-kb-write-guard.patch).
"""
from __future__ import annotations

import os
import time
from typing import Any, Iterable

from app.defense.control import (
    ControlAction,
    ControlOutcome,
    DefenseControl,
    DefenseDecision,
    DefenseStage,
)

from . import audit

DEFAULT_TRUSTED_TIERS = ("system",)


def trusted_tiers_from_env() -> frozenset[str]:
    raw = os.environ.get("CYBERAWARE_TRUSTED_TIERS", "")
    tiers = {t.strip().lower() for t in raw.split(",") if t.strip()}
    return frozenset(tiers or DEFAULT_TRUSTED_TIERS)


def exclusion_reason(candidate: dict[str, Any], trusted_tiers: Iterable[str]) -> str | None:
    """Why a chunk must not reach the model, or None if it is trusted."""
    if candidate.get("is_user_injected"):
        return "user-injected content"
    tier = str(candidate.get("trust_tier") or "user").lower()
    if tier not in trusted_tiers:
        return f"trust tier '{tier}' not allowlisted"
    return None


def _entry_id(candidate: dict[str, Any]) -> Any:
    meta = candidate.get("metadata") or {}
    return candidate.get("entry_id") or meta.get("entry_id")


class TrustGateControl(DefenseControl):
    id = "cyberaware.trust_gate"
    name = "Trust gate"
    verifies = (
        "retrieved chunks that users injected, or whose trust tier is not "
        "allowlisted, are excluded from the prompt context"
    )
    applies_to = (DefenseStage.RETRIEVAL,)

    def __init__(self, trusted_tiers: Iterable[str] | None = None) -> None:
        self.trusted_tiers = (
            frozenset(t.lower() for t in trusted_tiers)
            if trusted_tiers is not None
            else trusted_tiers_from_env()
        )

    async def _evaluate(self, decision: DefenseDecision) -> ControlOutcome:
        started = time.perf_counter()
        candidates = decision.context.setdefault("candidates", [])
        excluded: list[dict[str, Any]] = []
        for cand in candidates:
            if cand.get("excluded_by_control"):
                continue  # an earlier control already removed it
            reason = exclusion_reason(cand, self.trusted_tiers)
            if reason is None:
                continue
            # Both markers: apply_token_budget re-includes any chunk that lacks
            # excluded_by_control (app/rag/retrieval.py).
            cand["excluded_by_control"] = self.id
            cand["included_in_context"] = False
            cand["trust_reason"] = reason
            excluded.append({
                "chunk_id": cand.get("chunk_id") or cand.get("id"),
                "entry_id": _entry_id(cand),
                "title": cand.get("title") or (cand.get("metadata") or {}).get("title"),
                "reason": reason,
            })
        elapsed_ms = (time.perf_counter() - started) * 1000
        summary = f"excluded {len(excluded)} untrusted chunk(s)" if excluded else None
        if excluded:
            audit.record(
                control_id=self.id,
                surface=decision.surface,
                stage=decision.stage.value,
                level=decision.level,
                action=ControlAction.TRANSFORM.value,
                reason=summary,
                user_id=decision.user_id,
                elapsed_ms=elapsed_ms,
                excluded=excluded,
            )
        return ControlOutcome(
            action=ControlAction.TRANSFORM,
            payload=decision.payload,
            control_id=self.id,
            reason=summary,
            metadata={"excluded": len(excluded), "elapsed_ms": round(elapsed_ms, 3)},
        )
