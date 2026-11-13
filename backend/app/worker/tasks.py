"""Tarefas Celery (síncronas).

Cada acesso ao MongoDB passa por `run_with_db`, que cria loop e cliente próprios
(ver app.db.mongo). A coleta de rede (requests/Playwright/Instaloader) roda fora de
qualquer loop assíncrono, evitando conflito com a API síncrona do Playwright.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import timedelta

import redis
from bson import ObjectId
from celery.signals import worker_process_init

from app.core.config import get_settings
from app.core.logging import configure_logging, safe_error_summary
from app.core.timeutil import utcnow
from app.db.mongo import run_with_db
from app.services import runs
from app.services.inventory.fetchers import FetchError
from app.services.inventory.service import collect_inventory_sync, persist_inventory
from app.services.instagram.providers import get_provider
from app.services.instagram.service import persist_profile_result
from app.worker.celery_app import celery_app, enqueue_run

log = logging.getLogger(__name__)
settings = get_settings()
_redis: tuple[int, redis.Redis] | None = None

IG_BLOCK_KEY = "ig:blocked_until"


@worker_process_init.connect
def _init_process(**_):
    configure_logging(settings.log_level)


def redis_client() -> redis.Redis:
    """Cliente Redis por processo (criado após o fork do prefork)."""
    global _redis
    if _redis is None or _redis[0] != os.getpid():
        _redis = (os.getpid(), redis.Redis.from_url(settings.redis_url, socket_timeout=10))
    return _redis[1]


async def _begin(db, run_id: ObjectId, worker: str):
    run = await runs.start_run(db, run_id, worker)
    if run is None:
        return None
    company = await db.companies.find_one({"_id": run["company_id"]})
    return run, company


def _backoff(retries: int) -> int:
    return settings.task_retry_backoff_seconds * (2 ** retries)


def _lock(name: str):
    return redis_client().lock(name, timeout=settings.run_lease_minutes * 60, blocking=False)


@celery_app.task(bind=True, name="collect_inventory", max_retries=settings.task_max_retries)
def collect_inventory(self, run_id: str):
    rid = ObjectId(run_id)
    ctx = run_with_db(_begin, rid, self.request.hostname or "worker")
    if ctx is None:
        return {"skipped": "execução inexistente ou já processada"}
    run, company = ctx
    if company is None or not company.get("inventory_url"):
        run_with_db(runs.finish_run, rid, "skipped", error_summary="Empresa inexistente ou sem URL de estoque")
        return {"skipped": True}

    lock = _lock(f"lock:inventory:{company['_id']}")
    if not lock.acquire():
        run_with_db(runs.finish_run, rid, "skipped", error_summary="Outra coleta de estoque desta empresa em andamento")
        return {"skipped": True}
    try:
        try:
            outcome = collect_inventory_sync(company, settings)
        except FetchError as exc:
            summary = safe_error_summary(exc)
            if exc.transient and self.request.retries < settings.task_max_retries:
                countdown = _backoff(self.request.retries)
                run_with_db(runs.mark_retry, rid, summary, countdown)
                log.warning("Estoque %s: falha transitória, nova tentativa em %ss", company["name"], countdown)
                raise self.retry(exc=exc, countdown=countdown)
            run_with_db(runs.finish_run, rid, "failed", error_summary=summary, error_code="fetch")
            return {"status": "failed"}
        except Exception as exc:  # noqa: BLE001 - erro registrado e execução encerrada
            log.exception("Estoque %s: erro inesperado na coleta", company["name"])
            run_with_db(runs.finish_run, rid, "failed", error_summary=safe_error_summary(exc), error_code="parser")
            return {"status": "failed"}

        result = run_with_db(
            persist_inventory, company["_id"], rid, outcome, utcnow(), settings.inventory_min_ratio
        )
        if result["found"] == 0:
            run_with_db(
                runs.finish_run, rid, "failed",
                error_summary="Nenhum veículo extraído; estoque anterior preservado. "
                              "O layout do site pode ter mudado ou o parser não é adequado.",
                error_code="empty", details=result,
            )
            return {"status": "failed"}
        status = "success" if result["complete"] else "partial"
        run_with_db(runs.finish_run, rid, status, records=result["found"], partial=not result["complete"],
                    error_summary="; ".join(result["partial_reasons"]) or None, details=result)
        log.info("Estoque %s: %s (%s veículos)", company["name"], status, result["found"])
        return {"status": status, "found": result["found"]}
    finally:
        try:
            lock.release()
        except Exception:  # noqa: BLE001 - lock já expirado
            pass


@celery_app.task(bind=True, name="collect_instagram", max_retries=settings.task_max_retries,
                 rate_limit=settings.instagram_rate_limit)
def collect_instagram(self, run_id: str):
    rid = ObjectId(run_id)
    ctx = run_with_db(_begin, rid, self.request.hostname or "worker")
    if ctx is None:
        return {"skipped": "execução inexistente ou já processada"}
    run, company = ctx
    username = (company or {}).get("instagram_username")
    if not username:
        run_with_db(runs.finish_run, rid, "skipped", error_summary="Empresa sem perfil do Instagram")
        return {"skipped": True}

    r = redis_client()
    blocked_for = r.ttl(IG_BLOCK_KEY)
    if blocked_for and blocked_for > 0:
        message = f"Instagram limitou consultas recentemente; aguardando {blocked_for}s"
        if self.request.retries < settings.task_max_retries:
            run_with_db(runs.mark_retry, rid, message, blocked_for + 30)
            raise self.retry(countdown=blocked_for + 30)
        run_with_db(runs.finish_run, rid, "failed", error_summary=message, error_code="rate_limited")
        return {"status": "failed"}

    lock = _lock(f"lock:instagram:{username}")
    if not lock.acquire():
        run_with_db(runs.finish_run, rid, "skipped", error_summary="Outra coleta deste perfil em andamento")
        return {"skipped": True}
    try:
        provider = get_provider(settings)
        result = provider.fetch_profile(username, settings.instagram_posts_limit)
        if result.error_code == "rate_limited":
            block = settings.instagram_block_minutes * 60 * (2 ** self.request.retries)
            r.set(IG_BLOCK_KEY, utcnow().isoformat(), ex=block)
        if result.status == "failed" and result.retryable and self.request.retries < settings.task_max_retries:
            countdown = max(_backoff(self.request.retries), r.ttl(IG_BLOCK_KEY) or 0)
            run_with_db(runs.mark_retry, rid, f"{result.error_code}: {result.error_message or ''}"[:300], countdown)
            raise self.retry(countdown=countdown)

        summary = run_with_db(persist_profile_result, company["_id"], rid, username, result, utcnow())
        status = {"success": "success", "partial": "partial"}.get(result.status, "failed")
        error = None
        if result.status != "success":
            error = (result.error_code or "") + (f": {result.error_message}" if result.error_message else "")
            error = (error + (" | " + "; ".join(result.notes) if result.notes else ""))[:300]
        run_with_db(runs.finish_run, rid, status, records=summary["posts_collected"] + (1 if summary["followers"] is not None else 0),
                    partial=status == "partial", error_summary=error, error_code=result.error_code, details=summary)
        log.info("Instagram @%s: %s", username, status)
        return {"status": status}
    finally:
        try:
            lock.release()
        except Exception:  # noqa: BLE001
            pass


async def _schedule_due(db) -> list[dict]:
    now = utcnow()
    created = []
    async for company in db.companies.find({"active": True}):
        for source in ("inventory", "instagram"):
            hours = int(company.get(f"{source}_frequency_hours") or 0)
            if hours <= 0:
                continue
            if source == "instagram":
                if not company.get("instagram_username"):
                    continue
                hours = max(hours, settings.instagram_min_frequency_hours)
            if source == "inventory" and not company.get("inventory_url"):
                continue
            last = await runs.last_run(db, company["_id"], source)
            if last is not None and last["created_at"] + timedelta(hours=hours) > now:
                continue
            key = f"sched:{source}:{company['_id']}:{hours}:{runs.schedule_slot(now, hours)}"
            run, was_created = await runs.request_run(db, company["_id"], source, "agendada", "agendador", key, now)
            if was_created:
                created.append(run)
    return created


async def _mark_redispatched(db, run_ids: list[ObjectId]) -> None:
    if run_ids:
        await db.collection_runs.update_many({"_id": {"$in": run_ids}}, {"$set": {"redispatched_at": utcnow()},
                                                                          "$inc": {"redispatch_count": 1}})


@celery_app.task(name="scheduler_tick", ignore_result=True)
def scheduler_tick():
    # Batimento lido pelo healthcheck do scheduler: prova que o beat enfileira e o worker executa.
    redis_client().set("scheduler:last_tick", int(time.time()), ex=900)
    # Trava curta: evita duas verificações sobrepostas (ex.: tick lento).
    lock = redis_client().lock("lock:scheduler_tick", timeout=300, blocking=False)
    if not lock.acquire():
        return
    try:
        created = run_with_db(_schedule_due)
        for run in created:
            enqueue_run(run)
        stale = run_with_db(runs.stale_queued_runs)
        for run in stale:
            enqueue_run(run)
        run_with_db(_mark_redispatched, [r["_id"] for r in stale])
        if created or stale:
            log.info("Agendador: %s nova(s) execução(ões), %s reenviada(s)", len(created), len(stale))
    finally:
        try:
            lock.release()
        except Exception:  # noqa: BLE001
            pass
