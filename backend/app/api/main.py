"""Aplicação FastAPI. Todas as rotas ficam sob /api."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import auth, briefings, companies, dashboard, exports, instagram, inventory, runs
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.migrations import MIGRATIONS
from app.db.mongo import create_client, wait_for_mongo

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("app.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = create_client(settings)
    await wait_for_mongo(client)
    app.state.mongo = client
    app.state.db = client[settings.mongo_db]
    app.state.redis = aioredis.from_url(settings.redis_url, socket_timeout=5)
    applied = {d.get("version") async for d in app.state.db.schema_migrations.find({"version": {"$exists": True}})}
    missing = [m.version for m in MIGRATIONS if m.version not in applied]
    if missing:
        log.warning("Migrações pendentes %s: execute `python -m app.cli.migrate`", missing)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await client.close()


app = FastAPI(
    title="Monitor Automotivo — API",
    description="Estoque de veículos e presença pública no Instagram para briefings de marketing.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


MESSAGES_PT = {
    "missing": "Campo obrigatório",
    "string_too_short": "Deve ter pelo menos {min_length} caractere(s)",
    "string_too_long": "Deve ter no máximo {max_length} caracteres",
    "too_long": "Máximo de {max_length} itens",
    "int_parsing": "Informe um número inteiro",
    "int_from_float": "Informe um número inteiro",
    "float_parsing": "Informe um número",
    "greater_than_equal": "Deve ser maior ou igual a {ge}",
    "less_than_equal": "Deve ser menor ou igual a {le}",
    "literal_error": "Opção inválida",
    "datetime_parsing": "Data/hora inválida",
    "datetime_from_date_parsing": "Data/hora inválida",
    "bool_parsing": "Valor verdadeiro/falso inválido",
    "string_pattern_mismatch": "Formato inválido",
}


def _message_pt(error: dict) -> str:
    template = MESSAGES_PT.get(error.get("type", ""))
    if template:
        try:
            return template.format(**(error.get("ctx") or {}))
        except (KeyError, IndexError):
            return template
    message = error.get("msg", "").replace("Value error, ", "")
    if "email address" in message:
        return "E-mail inválido"
    return message


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    errors = [
        {"campo": ".".join(str(p) for p in e.get("loc", [])[1:]), "mensagem": _message_pt(e)}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": "Dados inválidos", "errors": errors})


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception):
    log.exception("Erro não tratado na API")
    return JSONResponse(status_code=500, content={"detail": "Erro interno. Consulte os logs do servidor."})


@app.get("/api/health", tags=["Saúde"])
async def health(request: Request):
    checks = {}
    try:
        await request.app.state.mongo.admin.command("ping")
        checks["mongo"] = "ok"
    except Exception:  # noqa: BLE001
        checks["mongo"] = "erro"
    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001
        checks["redis"] = "erro"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(status_code=200 if ok else 503, content={"status": "ok" if ok else "degradado", **checks})


for module in (auth, companies, inventory, instagram, runs, dashboard, briefings, exports):
    app.include_router(module.router, prefix="/api")
