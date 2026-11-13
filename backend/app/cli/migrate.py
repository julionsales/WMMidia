"""Aplica migrações/índices. Uso: python -m app.cli.migrate"""

from __future__ import annotations

import asyncio
import logging
import socket

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.migrations import run_migrations
from app.db.mongo import create_client, wait_for_mongo


async def main() -> None:
    settings = get_settings()
    client = create_client(settings)
    try:
        await wait_for_mongo(client)
        applied = await run_migrations(client[settings.mongo_db], owner=socket.gethostname())
        logging.getLogger("migrate").info("Migrações aplicadas agora: %s", applied or "nenhuma (já atualizado)")
    finally:
        await client.close()


if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    asyncio.run(main())
