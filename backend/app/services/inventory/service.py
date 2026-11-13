"""Coleta e persistência de estoque.

Regras de segurança do histórico:
- Um anúncio só é marcado como "não encontrado" após coleta COMPLETA e bem-sucedida.
- Coleta parcial (páginas com falha, total anunciado maior que o extraído, limite de
  páginas, queda brusca sem total anunciado) atualiza o que foi visto, mas não marca
  ausências.
- Coleta sem nenhum veículo é falha: nada é alterado.
- "Não encontrado na última coleta" NÃO significa venda.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace

from bson import ObjectId
from pymongo import UpdateOne
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import BulkWriteError

from app.core.config import Settings
from app.services.inventory.fetchers import BrowserFetcher, HttpFetcher
from app.services.inventory.normalize import NormalizedVehicle, normalize_and_dedupe
from app.services.inventory.parsers import get_parser
from app.services.inventory.parsers.base import ParseResult

log = logging.getLogger(__name__)

STATUS_ACTIVE = "ativo"
STATUS_MISSING = "nao_encontrado"


@dataclass
class CollectionOutcome:
    parser_key: str
    result: ParseResult
    vehicles: list[NormalizedVehicle]
    duplicates: int = 0
    invalid: int = 0
    requests_made: int = 0


@dataclass
class Completeness:
    complete: bool
    reasons: list[str] = field(default_factory=list)


def collect_inventory_sync(company: dict, settings: Settings) -> CollectionOutcome:
    """Executada no worker (síncrona, faz rede)."""
    url = company.get("inventory_url")
    if not url:
        raise ValueError("Empresa sem URL de estoque cadastrada")
    parser = get_parser(company.get("inventory_parser"), url)
    http = HttpFetcher(
        timeout=settings.scraper_timeout_seconds,
        max_redirects=settings.scraper_max_redirects,
        max_bytes=settings.scraper_max_bytes,
    )
    browser = BrowserFetcher(timeout_ms=settings.scraper_timeout_seconds * 1500) if settings.playwright_enabled else None
    fetchers = SimpleNamespace(http=http, browser=browser)
    result = parser.collect(url, fetchers, {"max_pages": settings.scraper_max_pages, "load_more": company.get("load_more", False)})
    vehicles, duplicates, invalid = normalize_and_dedupe(result.vehicles, result.final_url or url)
    return CollectionOutcome(parser.key, result, vehicles, duplicates, invalid, http.requests_made)


def assess_completeness(found: int, declared_total: int | None, reached_end: bool, pages_failed: int,
                        previous_active: int, min_ratio: float) -> Completeness:
    reasons: list[str] = []
    if found == 0:
        reasons.append("Nenhum veículo extraído")
    if pages_failed:
        reasons.append(f"{pages_failed} página(s) não puderam ser lidas")
    if not reached_end:
        reasons.append("A paginação foi interrompida antes do fim")
    if declared_total is not None and found < declared_total:
        reasons.append(f"Extraídos {found} de {declared_total} anunciados pelo site")
    if declared_total is None and previous_active and found < previous_active * min_ratio:
        reasons.append(
            f"Queda brusca sem total anunciado para confirmar ({found} vs. {previous_active} ativos antes)"
        )
    return Completeness(complete=not reasons, reasons=reasons)


def plan_vehicle_upsert(existing: dict | None, v: NormalizedVehicle, observed_at: datetime,
                        run_id: ObjectId) -> tuple[dict, dict, dict]:
    """Calcula ($set, $setOnInsert, observação) para um veículo visto nesta coleta."""
    attrs = {
        "key_type": v.key_type,
        "source_id": v.source_id,
        "brand": v.brand,
        "brand_display": v.brand_display,
        "model": v.model,
        "version": v.version,
        "year_fabrication": v.year_fabrication,
        "year_model": v.year_model,
        "km": v.km,
        "price": v.price,
        "price_on_request": v.price_on_request,
        "price_text": v.price_text,
        "url": v.url,
        "title": v.title,
        "status": STATUS_ACTIVE,
        "last_seen_at": observed_at,
        "last_seen_run_id": run_id,
        "missing_since": None,
    }
    observation = {
        "run_id": run_id,
        "observed_at": observed_at,
        "price": v.price,
        "price_on_request": v.price_on_request,
        "km": v.km,
        "previous_price": None,
        "price_changed": False,
    }
    on_insert = {"first_seen_at": observed_at, "first_price": v.price, "price_change_count": 0}
    if existing is None:
        observation["kind"] = "novo"
        return attrs, on_insert, observation

    already_this_run = existing.get("last_seen_run_id") == run_id
    observation["kind"] = "reapareceu" if existing.get("status") == STATUS_MISSING else "presente"
    previous = existing.get("price")
    if not already_this_run and previous is not None and v.price is not None and abs(previous - v.price) >= 0.01:
        observation["previous_price"] = previous
        observation["price_changed"] = True
        attrs["last_price_change_at"] = observed_at
        attrs["price_change_count"] = int(existing.get("price_change_count") or 0) + 1
    if observation["kind"] == "reapareceu":
        attrs["reappeared_at"] = observed_at
    return attrs, {k: on_insert[k] for k in ("first_seen_at", "first_price") if k not in existing}, observation


async def persist_inventory(db: AsyncDatabase, company_id: ObjectId, run_id: ObjectId, outcome: CollectionOutcome,
                            observed_at: datetime, min_ratio: float) -> dict:
    vehicles = outcome.vehicles
    previous_active = await db.vehicles.count_documents({"company_id": company_id, "status": STATUS_ACTIVE})
    check = assess_completeness(
        len(vehicles), outcome.result.declared_total, outcome.result.reached_end,
        outcome.result.pages_failed, previous_active, min_ratio,
    )
    summary = {
        "parser": outcome.parser_key,
        "found": len(vehicles),
        "declared_total": outcome.result.declared_total,
        "pages_fetched": outcome.result.pages_fetched,
        "pages_failed": outcome.result.pages_failed,
        "duplicates_discarded": outcome.duplicates,
        "invalid_discarded": outcome.invalid,
        "previous_active": previous_active,
        "complete": check.complete,
        "partial_reasons": check.reasons,
        "warnings": outcome.result.warnings,
        "new": 0,
        "reappeared": 0,
        "price_changes": 0,
        "marked_missing": 0,
    }
    if not vehicles:
        return summary

    keys = [v.vehicle_key for v in vehicles]
    existing = {
        d["vehicle_key"]: d
        async for d in db.vehicles.find({"company_id": company_id, "vehicle_key": {"$in": keys}})
    }
    ops = []
    observations = []
    for v in vehicles:
        current = existing.get(v.vehicle_key)
        set_fields, on_insert, obs = plan_vehicle_upsert(current, v, observed_at, run_id)
        update = {"$set": set_fields, "$inc": {"times_seen": 0 if current and current.get("last_seen_run_id") == run_id else 1}}
        if on_insert:
            update["$setOnInsert"] = on_insert
        ops.append(UpdateOne({"company_id": company_id, "vehicle_key": v.vehicle_key}, update, upsert=True))
        observations.append((v.vehicle_key, obs))
        summary["new"] += obs["kind"] == "novo"
        summary["reappeared"] += obs["kind"] == "reapareceu"
        summary["price_changes"] += bool(obs["price_changed"])
    await db.vehicles.bulk_write(ops, ordered=False)

    ids = {
        d["vehicle_key"]: d["_id"]
        async for d in db.vehicles.find({"company_id": company_id, "vehicle_key": {"$in": keys}}, {"vehicle_key": 1})
    }
    docs = [{**obs, "company_id": company_id, "vehicle_id": ids[key]} for key, obs in observations if key in ids]

    if check.complete:
        missing = [
            d["_id"]
            async for d in db.vehicles.find(
                {"company_id": company_id, "status": STATUS_ACTIVE, "last_seen_run_id": {"$ne": run_id}}, {"_id": 1}
            )
        ]
        if missing:
            await db.vehicles.update_many(
                {"_id": {"$in": missing}},
                {"$set": {"status": STATUS_MISSING, "missing_since": observed_at, "missing_run_id": run_id}},
            )
            docs.extend(
                {
                    "company_id": company_id,
                    "vehicle_id": vid,
                    "run_id": run_id,
                    "observed_at": observed_at,
                    "kind": "nao_encontrado",
                    "price": None,
                    "price_on_request": False,
                    "km": None,
                    "previous_price": None,
                    "price_changed": False,
                }
                for vid in missing
            )
        summary["marked_missing"] = len(missing)

    if docs:
        try:
            await db.inventory_observations.insert_many(docs, ordered=False)
        except BulkWriteError as exc:
            # Reentrega da mesma tarefa: observações (veículo, execução) já gravadas são ignoradas.
            non_dup = [e for e in exc.details.get("writeErrors", []) if e.get("code") != 11000]
            if non_dup:
                raise

    active_now = await db.vehicles.count_documents({"company_id": company_id, "status": STATUS_ACTIVE})
    company_update = {
        "inventory_summary.active_count": active_now,
        "inventory_summary.last_success_at": observed_at,
        "inventory_summary.last_run_id": run_id,
        "inventory_summary.last_found": len(vehicles),
    }
    if check.complete:
        company_update["inventory_summary.last_complete_at"] = observed_at
    await db.companies.update_one({"_id": company_id}, {"$set": company_update})
    summary["active_after"] = active_now
    return summary
