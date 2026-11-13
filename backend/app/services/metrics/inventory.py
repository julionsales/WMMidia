"""Indicadores de estoque (agregações no MongoDB + funções puras de apoio)."""

from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import ensure_utc, utcnow
from app.services.inventory.service import STATUS_ACTIVE, STATUS_MISSING

PRICE_BANDS = [
    (0, 50_000, "Até R$ 50 mil"),
    (50_000, 100_000, "R$ 50–100 mil"),
    (100_000, 150_000, "R$ 100–150 mil"),
    (150_000, 250_000, "R$ 150–250 mil"),
    (250_000, 400_000, "R$ 250–400 mil"),
    (400_000, None, "Acima de R$ 400 mil"),
]


def price_band(price: float | None, on_request: bool = False) -> str:
    if price is None:
        return "Sob consulta" if on_request else "Preço não informado"
    for low, high, label in PRICE_BANDS:
        if price >= low and (high is None or price < high):
            return label
    return PRICE_BANDS[-1][2]


def observed_days(first_seen: datetime, last_seen: datetime) -> float:
    return round((ensure_utc(last_seen) - ensure_utc(first_seen)).total_seconds() / 86400, 1)


def classify_models(models: list[dict], min_model_stock: int) -> list[dict]:
    """Categorias de conteúdo herdadas do script original (regras transparentes)."""
    out = []
    for row in models:
        stock, price_min = row["count"], row.get("price_min")
        if stock >= min_model_stock:
            category = "Giro de estoque"
        elif price_min is not None and price_min >= 400_000:
            category = "Hero car / Premium"
        elif price_min is not None and price_min <= 180_000:
            category = "Custo-benefício"
        else:
            category = "Oportunidade"
        out.append({**row, "content_category": category})
    return out


async def inventory_overview(db: AsyncDatabase, company_id: ObjectId, start: datetime, end: datetime,
                             min_model_stock: int = 3) -> dict:
    match_active = {"company_id": company_id, "status": STATUS_ACTIVE}
    active = [v async for v in db.vehicles.find(match_active)]
    observed_total = await db.vehicles.count_documents({"company_id": company_id})

    brands: dict[str, dict] = {}
    models: dict[tuple, dict] = {}
    bands: dict[str, int] = {}
    now = utcnow()
    for v in active:
        b = brands.setdefault(v["brand"], {"brand": v.get("brand_display") or v["brand"], "count": 0, "prices": []})
        b["count"] += 1
        key = (v["brand"], v["model"])
        m = models.setdefault(key, {"brand": v.get("brand_display") or v["brand"], "model": v["model"], "count": 0,
                                    "prices": [], "kms": []})
        m["count"] += 1
        if v.get("price") is not None:
            b["prices"].append(v["price"])
            m["prices"].append(v["price"])
        if v.get("km") is not None:
            m["kms"].append(v["km"])
        band = price_band(v.get("price"), v.get("price_on_request", False))
        bands[band] = bands.get(band, 0) + 1

    def finish(row: dict) -> dict:
        prices = row.pop("prices")
        kms = row.pop("kms", None)
        row["price_min"] = min(prices) if prices else None
        row["price_max"] = max(prices) if prices else None
        if kms is not None:
            row["km_avg"] = round(sum(kms) / len(kms)) if kms else None
        return row

    by_brand = sorted((finish(b) for b in brands.values()), key=lambda r: (-r["count"], r["brand"]))
    by_model = classify_models(
        sorted((finish(m) for m in models.values()), key=lambda r: (-r["count"], r["brand"], r["model"])),
        min_model_stock,
    )
    band_order = [label for _, _, label in PRICE_BANDS] + ["Sob consulta", "Preço não informado"]
    price_bands = [{"band": label, "count": bands[label]} for label in band_order if label in bands]

    longest = sorted(active, key=lambda v: v["first_seen_at"])[:10]
    new_in_period = await db.vehicles.count_documents(
        {"company_id": company_id, "first_seen_at": {"$gte": start, "$lte": end}}
    )
    missing_in_period = await db.vehicles.count_documents(
        {"company_id": company_id, "status": STATUS_MISSING, "missing_since": {"$gte": start, "$lte": end}}
    )
    changes_cursor = db.inventory_observations.find(
        {"company_id": company_id, "price_changed": True, "observed_at": {"$gte": start, "$lte": end}}
    ).sort("observed_at", -1).limit(200)
    changes = [c async for c in changes_cursor]
    vehicle_ids = list({c["vehicle_id"] for c in changes})
    vmap = {v["_id"]: v async for v in db.vehicles.find({"_id": {"$in": vehicle_ids}})}
    price_changes = [
        {
            "vehicle_id": c["vehicle_id"],
            "observed_at": c["observed_at"],
            "previous_price": c["previous_price"],
            "price": c["price"],
            "delta": (c["price"] - c["previous_price"]) if c["price"] is not None and c["previous_price"] else None,
            "brand": vmap.get(c["vehicle_id"], {}).get("brand_display"),
            "model": vmap.get(c["vehicle_id"], {}).get("model"),
            "version": vmap.get(c["vehicle_id"], {}).get("version"),
            "url": vmap.get(c["vehicle_id"], {}).get("url"),
        }
        for c in changes
    ]
    days = [observed_days(v["first_seen_at"], v.get("last_seen_at") or now) for v in active]
    company = await db.companies.find_one({"_id": company_id}, {"inventory_summary": 1})
    return {
        "active_count": len(active),
        "observed_total": observed_total,
        "by_brand": by_brand,
        "by_model": by_model,
        "price_bands": price_bands,
        "new_in_period": new_in_period,
        "missing_in_period": missing_in_period,
        "price_changes": price_changes,
        "observed_days": {
            "avg": round(sum(days) / len(days), 1) if days else None,
            "max": max(days) if days else None,
            "note": "Tempo observado = da primeira à última coleta em que o anúncio apareceu; "
                    "não é o tempo real de estoque da loja.",
        },
        "longest_observed": [
            {
                "id": v["_id"], "brand": v.get("brand_display"), "model": v["model"], "version": v.get("version"),
                "year_model": v.get("year_model"), "price": v.get("price"), "url": v.get("url"),
                "first_seen_at": v["first_seen_at"], "last_seen_at": v.get("last_seen_at"),
                "observed_days": observed_days(v["first_seen_at"], v.get("last_seen_at") or now),
            }
            for v in longest
        ],
        "summary": (company or {}).get("inventory_summary") or {},
        "missing_label": "Não encontrado na última coleta (não indica venda confirmada)",
    }
