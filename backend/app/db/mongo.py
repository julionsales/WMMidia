"""Clientes MongoDB (PyMongo assíncrono).

Estratégia de ciclo de vida:
- API (FastAPI/uvicorn): um AsyncMongoClient por processo, criado no lifespan e
  fechado no shutdown; vive no loop do uvicorn.
- Worker/Scheduler (Celery, tarefas síncronas): cada chamada a `run_with_db` executa
  `asyncio.run`, que cria um loop novo; o cliente é criado DENTRO desse loop e fechado
  ao final. Nenhum cliente assíncrono é compartilhado entre processos (prefork) ou loops.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timezone
from typing import Any, Awaitable, Callable, TypeVar

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings, get_settings

T = TypeVar("T")
log = logging.getLogger(__name__)


def create_client(settings: Settings | None = None) -> AsyncMongoClient:
    settings = settings or get_settings()
    return AsyncMongoClient(
        settings.mongo_uri,
        tz_aware=True,
        tzinfo=timezone.utc,
        serverSelectionTimeoutMS=8000,
        appname=settings.app_name,
    )


async def wait_for_mongo(client: AsyncMongoClient, attempts: int = 30, delay: float = 2.0) -> None:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            await client.admin.command("ping")
            return
        except Exception as exc:  # noqa: BLE001 - qualquer falha de conexão
            last = exc
            log.warning("MongoDB indisponível (tentativa %s/%s)", attempt, attempts)
            await asyncio.sleep(min(delay * attempt, 10))
    raise RuntimeError("MongoDB não respondeu após várias tentativas") from last


def run_with_db(fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
    """Executa uma corrotina de serviço em loop próprio, com cliente próprio."""
    settings = get_settings()

    async def _main() -> T:
        client = create_client(settings)
        try:
            return await fn(client[settings.mongo_db], *args, **kwargs)
        finally:
            await client.close()

    return asyncio.run(_main())


DB = AsyncDatabase
