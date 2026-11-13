"""Aplicação Celery (broker e coordenação via Redis).

A API importa este módulo apenas para publicar tarefas (`send_task` por nome), sem
carregar Playwright/Instaloader.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("monitor", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=False,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3 * 3600},
    task_routes={
        "collect_inventory": {"queue": "inventory"},
        "collect_instagram": {"queue": "instagram"},
        "scheduler_tick": {"queue": "default"},
    },
    task_default_queue="default",
    beat_schedule={
        "scheduler-tick": {"task": "scheduler_tick", "schedule": float(settings.scheduler_tick_seconds)},
    },
    include=["app.worker.tasks"],
)


def enqueue_run(run: dict) -> None:
    task = "collect_inventory" if run["source"] == "inventory" else "collect_instagram"
    run_id = str(run["_id"])
    # task_id = run_id: rastreabilidade entre Mongo, Celery e logs.
    celery_app.send_task(task, args=[run_id], task_id=run_id)
