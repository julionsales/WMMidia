"""Ciclo de vida das execuções de coleta (collection_runs).

O estado fica no MongoDB, independente do backend de resultados do Celery.

Idempotência e concorrência:
- `active_key` = "<fonte>:<empresa>" existe somente enquanto a execução está ativa
  (queued/running/retrying). Índice único parcial impede duas execuções ativas para a
  mesma empresa e fonte. Execuções ativas com lease vencido são marcadas "abandoned".
- `idempotency_key` (agendador: "sched:<fonte>:<empresa>:<janela>") impede duplicar o
  mesmo agendamento mesmo que o scheduler rode a verificação duas vezes.
- `start_run` só transiciona queued/retrying -> running uma vez por entrega; entregas
  duplicadas da mesma tarefa são ignoradas.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.core.timeutil import utcnow

Source = Literal["inventory", "instagram"]
ACTIVE_STATUSES = ("queued", "running", "retrying")
FINAL_STATUSES = ("success", "partial", "failed", "skipped", "abandoned")


def active_key(source: str, company_id: ObjectId) -> str:
    return f"{source}:{company_id}"


async def request_run(db: AsyncDatabase, company_id: ObjectId, source: Source, trigger: str,
                      requested_by: str | None = None, idempotency_key: str | None = None,
                      now: datetime | None = None) -> tuple[dict, bool]:
    """Cria uma execução 'queued'. Retorna (execução, criada_agora)."""
    settings = get_settings()
    now = now or utcnow()
    doc = {
        "company_id": company_id,
        "source": source,
        "trigger": trigger,
        "requested_by": requested_by,
        "status": "queued",
        "active_key": active_key(source, company_id),
        "created_at": now,
        "lease_expires_at": now + timedelta(minutes=settings.run_lease_minutes),
        "attempts": 0,
        "records": 0,
        "partial": False,
    }
    if idempotency_key:
        doc["idempotency_key"] = idempotency_key

    for _ in range(2):
        try:
            result = await db.collection_runs.insert_one(dict(doc))
            return {**doc, "_id": result.inserted_id}, True
        except DuplicateKeyError as exc:
            if idempotency_key and "idempotency_key" in str(exc):
                existing = await db.collection_runs.find_one({"idempotency_key": idempotency_key})
                if existing:
                    return existing, False
            existing = await db.collection_runs.find_one({"active_key": doc["active_key"]})
            if existing is None:
                continue  # terminou entre a inserção e a busca: tenta de novo
            if existing.get("lease_expires_at") and existing["lease_expires_at"] < now:
                await db.collection_runs.update_one(
                    {"_id": existing["_id"], "active_key": doc["active_key"]},
                    {
                        "$set": {"status": "abandoned", "finished_at": now,
                                 "error_summary": "Execução sem resposta do worker dentro do prazo"},
                        "$unset": {"active_key": ""},
                    },
                )
                continue
            return existing, False
    raise RuntimeError("Não foi possível registrar a execução")


async def start_run(db: AsyncDatabase, run_id: ObjectId, worker: str) -> dict | None:
    settings = get_settings()
    now = utcnow()
    return await db.collection_runs.find_one_and_update(
        {
            "_id": run_id,
            "$or": [
                {"status": {"$in": ["queued", "retrying"]}},
                # Reentrega após queda do worker: só retoma se o lease venceu.
                {"status": "running", "lease_expires_at": {"$lt": now}},
            ],
        },
        {
            "$set": {
                "status": "running",
                "started_at": now,
                "worker": worker,
                "lease_expires_at": now + timedelta(minutes=settings.run_lease_minutes),
            },
            "$inc": {"attempts": 1},
        },
        return_document=ReturnDocument.AFTER,
    )


async def mark_retry(db: AsyncDatabase, run_id: ObjectId, error_summary: str, countdown: int) -> None:
    settings = get_settings()
    now = utcnow()
    await db.collection_runs.update_one(
        {"_id": run_id, "status": "running"},
        {
            "$set": {
                "status": "retrying",
                "last_error": error_summary,
                "next_attempt_at": now + timedelta(seconds=countdown),
                "lease_expires_at": now + timedelta(seconds=countdown) + timedelta(minutes=settings.run_lease_minutes),
            }
        },
    )


async def finish_run(db: AsyncDatabase, run_id: ObjectId, status: str, records: int = 0, partial: bool = False,
                     error_summary: str | None = None, error_code: str | None = None,
                     details: dict | None = None) -> None:
    assert status in FINAL_STATUSES
    now = utcnow()
    update: dict = {
        "$set": {
            "status": status,
            "finished_at": now,
            "records": records,
            "partial": partial,
            "error_summary": error_summary,
            "error_code": error_code,
            "details": details or {},
        },
        "$unset": {"active_key": "", "next_attempt_at": ""},
    }
    await db.collection_runs.update_one({"_id": run_id}, update)


async def stale_queued_runs(db: AsyncDatabase, older_than_minutes: int = 15) -> list[dict]:
    """Execuções que ficaram em fila (ex.: falha ao publicar no broker) para reenvio."""
    limit = utcnow() - timedelta(minutes=older_than_minutes)
    cursor = db.collection_runs.find(
        {"status": "queued", "created_at": {"$lt": limit}, "lease_expires_at": {"$gt": utcnow()}}
    ).limit(50)
    return [r async for r in cursor]


async def last_run(db: AsyncDatabase, company_id: ObjectId, source: str) -> dict | None:
    return await db.collection_runs.find_one(
        {"company_id": company_id, "source": source}, sort=[("created_at", -1)]
    )


def next_scheduled_at(company: dict, source: str, last: dict | None) -> datetime | None:
    hours = company.get(f"{source}_frequency_hours") or 0
    if not company.get("active") or hours <= 0:
        return None
    if source == "inventory" and not company.get("inventory_url"):
        return None
    if source == "instagram" and not company.get("instagram_username"):
        return None
    if last is None:
        return utcnow()
    return last["created_at"] + timedelta(hours=hours)


def schedule_slot(now: datetime, hours: int) -> int:
    return int(now.timestamp() // (hours * 3600))
