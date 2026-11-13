"""Testes com MongoDB real (sem rede externa). Rodam com TEST_MONGO_URI definido:
docker compose --profile test run --rm tests
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.db.migrations import run_migrations
from app.services import runs
from app.services.instagram.providers.base import PostData, ProfileData, ProfileFetchResult
from app.services.instagram.service import persist_profile_result
from app.services.inventory.normalize import RawVehicle, normalize_and_dedupe
from app.services.inventory.parsers.base import ParseResult
from app.services.inventory.service import CollectionOutcome, persist_inventory

pytestmark = pytest.mark.mongo
T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
async def db():
    from pymongo import AsyncMongoClient

    client = AsyncMongoClient(os.environ["TEST_MONGO_URI"], tz_aware=True)
    database = client[f"test_{uuid.uuid4().hex[:10]}"]
    await run_migrations(database, owner="pytest")
    yield database
    await client.drop_database(database.name)
    await client.close()


async def _company(db, **extra):
    cid = ObjectId()
    await db.companies.insert_one({"_id": cid, "name": "Loja", "slug": f"loja-{cid}", "active": True, **extra})
    return cid


def outcome(ids, declared=None, failed_pages=0, prices=None):
    prices = prices or {}
    raws = [RawVehicle(brand="AUDI", model=f"M{i}", source_id=str(i), price_text=prices.get(i, "R$ 100.000")) for i in ids]
    vehicles, dup, inv = normalize_and_dedupe(raws)
    result = ParseResult(vehicles=raws, declared_total=declared, pages_fetched=1, pages_failed=failed_pages)
    return CollectionOutcome("test", result, vehicles, dup, inv)


async def test_migrations_are_idempotent(db):
    assert await run_migrations(db, owner="again") == []
    names = {i["name"] async for i in await db.vehicles.list_indexes()}
    assert "uniq_company_vehicle_key" in names


async def test_request_run_prevents_parallel_and_honors_idempotency_key(db):
    cid = await _company(db)
    first, created = await runs.request_run(db, cid, "inventory", "manual")
    again, created_again = await runs.request_run(db, cid, "inventory", "manual")
    assert created and not created_again and again["_id"] == first["_id"]
    other, created_other = await runs.request_run(db, cid, "instagram", "manual")
    assert created_other and other["_id"] != first["_id"]
    await runs.finish_run(db, first["_id"], "success")
    sched, c1 = await runs.request_run(db, cid, "inventory", "agendada", idempotency_key="sched:x:1")
    await runs.finish_run(db, sched["_id"], "success")
    dup, c2 = await runs.request_run(db, cid, "inventory", "agendada", idempotency_key="sched:x:1")
    assert c1 and not c2 and dup["_id"] == sched["_id"]


async def test_expired_lease_is_abandoned(db):
    cid = await _company(db)
    old, _ = await runs.request_run(db, cid, "inventory", "manual", now=T0)
    new, created = await runs.request_run(db, cid, "inventory", "manual")
    assert created and new["_id"] != old["_id"]
    assert (await db.collection_runs.find_one({"_id": old["_id"]}))["status"] == "abandoned"


async def test_start_run_only_once(db):
    cid = await _company(db)
    run, _ = await runs.request_run(db, cid, "inventory", "manual")
    assert await runs.start_run(db, run["_id"], "w1") is not None
    assert await runs.start_run(db, run["_id"], "w2") is None  # entrega duplicada é ignorada


async def test_inventory_history_survives_partial_and_failed_runs(db):
    cid = await _company(db)
    r1 = ObjectId()
    s1 = await persist_inventory(db, cid, r1, outcome([1, 2, 3], declared=3), T0, 0.5)
    assert s1["complete"] and s1["new"] == 3

    # Coleta parcial (total anunciado maior): nada é marcado como ausente.
    s2 = await persist_inventory(db, cid, ObjectId(), outcome([1], declared=3), T0 + timedelta(days=1), 0.5)
    assert not s2["complete"] and s2["marked_missing"] == 0
    assert await db.vehicles.count_documents({"company_id": cid, "status": "ativo"}) == 3

    # Coleta vazia (falha): estoque preservado.
    s3 = await persist_inventory(db, cid, ObjectId(), outcome([]), T0 + timedelta(days=2), 0.5)
    assert s3["found"] == 0 and await db.vehicles.count_documents({"company_id": cid, "status": "ativo"}) == 3

    # Página com falha: parcial.
    s4 = await persist_inventory(db, cid, ObjectId(), outcome([1, 2], failed_pages=1), T0 + timedelta(days=3), 0.5)
    assert not s4["complete"] and s4["marked_missing"] == 0

    # Coleta completa sem o veículo 3: marcado como não encontrado (não vendido).
    r5 = ObjectId()
    s5 = await persist_inventory(db, cid, r5, outcome([1, 2], declared=2, prices={1: "R$ 95.000"}), T0 + timedelta(days=4), 0.5)
    assert s5["complete"] and s5["marked_missing"] == 1 and s5["price_changes"] == 1
    missing = await db.vehicles.find_one({"company_id": cid, "vehicle_key": "id:3"})
    assert missing["status"] == "nao_encontrado" and missing["missing_since"] == T0 + timedelta(days=4)

    # Reprocessar a mesma execução não duplica observações.
    before = await db.inventory_observations.count_documents({"run_id": r5})
    await persist_inventory(db, cid, r5, outcome([1, 2], declared=2, prices={1: "R$ 95.000"}), T0 + timedelta(days=4), 0.5)
    assert await db.inventory_observations.count_documents({"run_id": r5}) == before

    # Reaparecimento.
    s6 = await persist_inventory(db, cid, ObjectId(), outcome([1, 2, 3], declared=3, prices={1: "R$ 95.000"}),
                                 T0 + timedelta(days=5), 0.5)
    assert s6["reappeared"] == 1
    vehicle = await db.vehicles.find_one({"company_id": cid, "vehicle_key": "id:1"})
    assert vehicle["first_seen_at"] == T0 and vehicle["price_change_count"] == 1


def ig_result(status, followers=None, posts=(), error=None):
    profile = ProfileData(username="loja", followers=followers, following=10, media_count=50) if followers is not None or status != "failed" else None
    return ProfileFetchResult(status=status, source="test", profile=profile, posts=list(posts), error_code=error)


async def test_instagram_failure_preserves_last_valid_result(db):
    cid = await _company(db, instagram_username="loja")
    post = PostData(shortcode="ABC", url="https://www.instagram.com/p/ABC/", taken_at=T0, likes=10, comments=None)
    await persist_profile_result(db, cid, ObjectId(), "loja", ig_result("success", 1000, [post]), T0)
    await persist_profile_result(db, cid, ObjectId(), "loja", ig_result("failed", error="rate_limited"), T0 + timedelta(days=1))
    profile = await db.instagram_profiles.find_one({"username": "loja"})
    assert profile["latest"]["followers"] == 1000 and profile["last_status"] == "failed"
    assert await db.instagram_snapshots.count_documents({"profile_id": profile["_id"]}) == 2

    post2 = PostData(shortcode="ABC", url="https://www.instagram.com/p/ABC/", taken_at=T0, likes=15, comments=2)
    await persist_profile_result(db, cid, ObjectId(), "loja", ig_result("success", 1010, [post2]), T0 + timedelta(days=2))
    assert await db.instagram_posts.count_documents({"profile_id": profile["_id"]}) == 1
    history = [m async for m in db.instagram_post_metrics.find({}).sort("observed_at", 1)]
    assert [(m["likes"], m["comments"]) for m in history] == [(10, None), (15, 2)]  # None preservado, não zero
