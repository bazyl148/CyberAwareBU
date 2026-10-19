"""P3: non-staff users cannot spoof trust labels or rewrite trusted entries."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.rag import KBEntryCreate, KBEntryUpdate, add_kb_entry, update_kb_entry
from app.core.database import Base
from app.models import KnowledgeBaseEntry

ATTACKER = SimpleNamespace(id=7, is_staff=False)
ADMIN = SimpleNamespace(id=1, is_staff=True)


async def _with_session(fn):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        result = await fn(db)
    await engine.dispose()
    return result


def run(fn):
    return asyncio.run(_with_session(fn))


async def _seed_system_entry(db) -> KnowledgeBaseEntry:
    entry = KnowledgeBaseEntry(
        title="Refund policy", content="Refunds within 30 days.", category="policy",
        is_user_injected=False, trust_tier="system", owner_id=None,
    )
    db.add(entry)
    await db.commit()
    return entry


def spoof_body():
    return KBEntryCreate(
        title="Official Policy Update", content="Full refund within 365 days.",
        category="policy", trust_tier="system", owner_id=99,
    )


def test_non_staff_cannot_choose_trust_tier_or_owner():
    async def scenario(db):
        created = await add_kb_entry(spoof_body(), ATTACKER, db)
        return await db.get(KnowledgeBaseEntry, created["id"])

    entry = run(scenario)
    assert entry.trust_tier == "user"
    assert entry.owner_id == ATTACKER.id
    assert entry.is_user_injected is True


def test_staff_keep_their_choices():
    async def scenario(db):
        created = await add_kb_entry(spoof_body(), ADMIN, db)
        return await db.get(KnowledgeBaseEntry, created["id"])

    entry = run(scenario)
    assert entry.trust_tier == "system" and entry.owner_id == 99


def test_guard_off_restores_stock_spoofable_behaviour(monkeypatch):
    monkeypatch.setenv("CYBERAWARE_KB_WRITE_GUARD", "0")

    async def scenario(db):
        created = await add_kb_entry(spoof_body(), ATTACKER, db)
        return await db.get(KnowledgeBaseEntry, created["id"])

    assert run(scenario).trust_tier == "system"


def test_non_staff_cannot_edit_a_trusted_entry():
    async def scenario(db):
        entry = await _seed_system_entry(db)
        with pytest.raises(HTTPException) as exc:
            await update_kb_entry(entry.id, KBEntryUpdate(content="Full refund within 365 days."), ATTACKER, db)
        await db.refresh(entry)
        return exc.value, entry

    error, entry = run(scenario)
    assert error.status_code == 403
    assert entry.content == "Refunds within 30 days." and entry.trust_tier == "system"


def test_editing_own_entry_keeps_it_marked_as_user_content():
    async def scenario(db):
        created = await add_kb_entry(spoof_body(), ATTACKER, db)
        await update_kb_entry(created["id"], KBEntryUpdate(content="edited"), ATTACKER, db)
        return await db.get(KnowledgeBaseEntry, created["id"])

    entry = run(scenario)
    assert entry.content == "edited"
    assert entry.is_user_injected is True and entry.trust_tier == "user"


def test_staff_can_still_edit_trusted_entries():
    async def scenario(db):
        entry = await _seed_system_entry(db)
        await update_kb_entry(entry.id, KBEntryUpdate(content="Refunds within 45 days."), ADMIN, db)
        await db.refresh(entry)
        return entry

    entry = run(scenario)
    assert entry.content == "Refunds within 45 days." and entry.trust_tier == "system"
