"""Migrações versionadas e idempotentes (índices e ajustes de estrutura).

Executadas explicitamente pelo serviço `init` do Docker Compose
(`python -m app.cli.migrate`). API e worker NÃO criam índices ao iniciar,
evitando corrida entre serviços. Um documento-trava em `schema_migrations`
garante uma única execução simultânea.

Nenhum índice TTL é criado: dados de negócio e históricos não expiram.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Awaitable, Callable

from pymongo import ASCENDING as ASC
from pymongo import DESCENDING as DESC
from pymongo import IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.timeutil import utcnow

log = logging.getLogger(__name__)

LOCK_ID = "__lock__"


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    apply: Callable[[AsyncDatabase], Awaitable[None]]


def _exists(field: str) -> dict:
    return {field: {"$exists": True}}


async def _m001_indexes(db: AsyncDatabase) -> None:
    specs: dict[str, list[IndexModel]] = {
        "users": [IndexModel([("email", ASC)], unique=True, name="uniq_email")],
        "companies": [
            IndexModel([("slug", ASC)], unique=True, name="uniq_slug"),
            IndexModel([("name_lower", ASC)], name="name_lower"),
            IndexModel([("active", ASC), ("name_lower", ASC)], name="active_name"),
            IndexModel([("instagram_username", ASC)], name="instagram_username"),
        ],
        "vehicles": [
            IndexModel([("company_id", ASC), ("vehicle_key", ASC)], unique=True, name="uniq_company_vehicle_key"),
            IndexModel([("company_id", ASC), ("status", ASC)], name="company_status"),
            IndexModel([("company_id", ASC), ("brand", ASC), ("model", ASC)], name="company_brand_model"),
            IndexModel([("company_id", ASC), ("first_seen_at", DESC)], name="company_first_seen"),
            IndexModel([("company_id", ASC), ("missing_since", DESC)], name="company_missing_since"),
            IndexModel([("company_id", ASC), ("last_seen_at", DESC)], name="company_last_seen"),
        ],
        "inventory_observations": [
            IndexModel([("vehicle_id", ASC), ("run_id", ASC)], unique=True, name="uniq_vehicle_run"),
            IndexModel([("vehicle_id", ASC), ("observed_at", ASC)], name="vehicle_observed"),
            IndexModel([("company_id", ASC), ("observed_at", DESC)], name="company_observed"),
            IndexModel([("company_id", ASC), ("price_changed", ASC), ("observed_at", DESC)], name="company_price_changes"),
        ],
        "instagram_profiles": [
            IndexModel([("username", ASC)], unique=True, name="uniq_username"),
            IndexModel([("company_id", ASC)], name="company"),
        ],
        "instagram_snapshots": [
            IndexModel([("profile_id", ASC), ("collected_at", DESC)], name="profile_collected"),
            IndexModel([("company_id", ASC), ("collected_at", DESC)], name="company_collected"),
            IndexModel([("profile_id", ASC), ("status", ASC), ("collected_at", DESC)], name="profile_status_collected"),
        ],
        "instagram_posts": [
            IndexModel([("profile_id", ASC), ("shortcode", ASC)], unique=True, name="uniq_profile_shortcode"),
            IndexModel([("company_id", ASC), ("taken_at", DESC)], name="company_taken"),
            IndexModel([("profile_id", ASC), ("taken_at", DESC)], name="profile_taken"),
        ],
        "instagram_post_metrics": [
            IndexModel([("post_id", ASC), ("observed_at", DESC)], name="post_observed"),
            IndexModel(
                [("post_id", ASC), ("run_id", ASC)],
                unique=True,
                partialFilterExpression=_exists("run_id"),
                name="uniq_post_run",
            ),
            IndexModel([("company_id", ASC), ("observed_at", DESC)], name="company_observed"),
        ],
        "collection_runs": [
            IndexModel(
                [("idempotency_key", ASC)],
                unique=True,
                partialFilterExpression={"idempotency_key": {"$type": "string"}},
                name="uniq_idempotency_key",
            ),
            IndexModel(
                [("active_key", ASC)],
                unique=True,
                partialFilterExpression={"active_key": {"$type": "string"}},
                name="uniq_active_key",
            ),
            IndexModel([("company_id", ASC), ("source", ASC), ("created_at", DESC)], name="company_source_created"),
            IndexModel([("status", ASC), ("created_at", DESC)], name="status_created"),
            IndexModel([("created_at", DESC)], name="created"),
        ],
        "briefings": [
            IndexModel([("company_id", ASC), ("version", DESC)], unique=True, name="uniq_company_version"),
            IndexModel([("created_at", DESC)], name="created"),
        ],
        "post_vehicle_links": [
            IndexModel([("post_id", ASC), ("vehicle_id", ASC)], unique=True, name="uniq_post_vehicle"),
            IndexModel([("company_id", ASC)], name="company"),
            IndexModel([("vehicle_id", ASC)], name="vehicle"),
        ],
    }
    for collection, indexes in specs.items():
        await db[collection].create_indexes(indexes)
        log.info("Índices garantidos em %s (%d)", collection, len(indexes))


async def _m002_snapshot_per_run(db: AsyncDatabase) -> None:
    # Reentrega da mesma tarefa não pode gerar dois snapshots para a mesma execução.
    await db.instagram_snapshots.create_indexes([
        IndexModel(
            [("profile_id", ASC), ("run_id", ASC)],
            unique=True,
            partialFilterExpression={"run_id": {"$type": "objectId"}},
            name="uniq_profile_run",
        )
    ])


MIGRATIONS: list[Migration] = [
    Migration(1, "Índices iniciais de todas as coleções", _m001_indexes),
    Migration(2, "Snapshot único por execução de coleta", _m002_snapshot_per_run),
]


async def _acquire_lock(db: AsyncDatabase, owner: str, wait_seconds: int = 120) -> None:
    coll = db.schema_migrations
    deadline = utcnow() + timedelta(seconds=wait_seconds)
    while True:
        now = utcnow()
        # Trava expirada (processo morreu) é removida.
        await coll.delete_one({"_id": LOCK_ID, "expires_at": {"$lt": now}})
        try:
            await coll.insert_one({"_id": LOCK_ID, "owner": owner, "expires_at": now + timedelta(minutes=10)})
            return
        except DuplicateKeyError:
            if utcnow() > deadline:
                raise RuntimeError("Outra migração está em andamento há muito tempo.")
            await asyncio.sleep(2)


async def run_migrations(db: AsyncDatabase, owner: str = "cli") -> list[int]:
    await _acquire_lock(db, owner)
    applied: list[int] = []
    try:
        done = {d["version"] async for d in db.schema_migrations.find({"version": {"$exists": True}})}
        for migration in MIGRATIONS:
            if migration.version in done:
                continue
            log.info("Aplicando migração %s: %s", migration.version, migration.description)
            await migration.apply(db)
            await db.schema_migrations.update_one(
                {"_id": f"v{migration.version:04d}"},
                {"$set": {"version": migration.version, "description": migration.description, "applied_at": utcnow()}},
                upsert=True,
            )
            applied.append(migration.version)
        # Índices são idempotentes; reaplicar a v1 garante índices novos adicionados ao código.
        if 1 in done:
            await _m001_indexes(db)
    finally:
        await db.schema_migrations.delete_one({"_id": LOCK_ID, "owner": owner})
    return applied
