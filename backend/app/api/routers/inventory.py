from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import Period, current_user, get_company, get_db
from app.core.timeutil import utcnow
from app.models.common import page_payload, serialize, to_object_id
from app.services.metrics.inventory import inventory_overview, observed_days

router = APIRouter(prefix="/inventory", tags=["Estoque"])

SORTS = {
    "brand": "brand", "model": "model", "year": "year_model", "price": "price", "km": "km",
    "first_seen": "first_seen_at", "last_seen": "last_seen_at",
}


def vehicle_filter(company_id: str | None, brand: str | None, model: str | None, year_min: int | None,
                   year_max: int | None, price_min: float | None, price_max: float | None,
                   status: str | None, search: str | None) -> dict:
    query: dict = {}
    if company_id:
        query["company_id"] = to_object_id(company_id, "empresa")
    if brand:
        query["brand"] = brand.upper()
    if model:
        query["model"] = model.upper()
    if year_min or year_max:
        query["year_model"] = {k: v for k, v in (("$gte", year_min), ("$lte", year_max)) if v}
    if price_min is not None or price_max is not None:
        query["price"] = {k: v for k, v in (("$gte", price_min), ("$lte", price_max)) if v is not None}
    if status in ("ativo", "nao_encontrado"):
        query["status"] = status
    if search:
        pattern = re.escape(search.strip().upper())
        query["$or"] = [{"model": {"$regex": pattern}}, {"version": {"$regex": pattern}}, {"brand": {"$regex": pattern}}]
    return query


@router.get("/vehicles")
async def list_vehicles(
    company_id: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    year_min: int | None = Query(None, ge=1950, le=2100),
    year_max: int | None = Query(None, ge=1950, le=2100),
    price_min: float | None = Query(None, ge=0),
    price_max: float | None = Query(None, ge=0),
    status: str | None = Query("ativo"),
    search: str | None = Query(None, max_length=80),
    sort: str = "brand",
    order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    db: AsyncDatabase = Depends(get_db),
    _user: dict = Depends(current_user),
):
    query = vehicle_filter(company_id, brand, model, year_min, year_max, price_min, price_max, status, search)
    total = await db.vehicles.count_documents(query)
    direction = 1 if order == "asc" else -1
    sort_spec = [(SORTS.get(sort, "brand"), direction), ("model", 1), ("_id", 1)]
    cursor = db.vehicles.find(query).sort(sort_spec).skip((page - 1) * size).limit(size)
    items = [v async for v in cursor]
    names = {c["_id"]: c["name"] async for c in db.companies.find({"_id": {"$in": list({v["company_id"] for v in items})}}, {"name": 1})}
    now = utcnow()
    for v in items:
        v["company_name"] = names.get(v["company_id"])
        v["observed_days"] = observed_days(v["first_seen_at"], v.get("last_seen_at") or now)
    return page_payload(items, total, page, size)


@router.get("/facets")
async def facets(company_id: str | None = None, db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    match: dict = {"status": "ativo"}
    if company_id:
        match["company_id"] = to_object_id(company_id, "empresa")
    brands = [r async for r in await db.vehicles.aggregate([
        {"$match": match},
        {"$group": {"_id": "$brand", "label": {"$first": "$brand_display"}, "models": {"$addToSet": "$model"}, "n": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ])]
    return [{"brand": b["_id"], "label": b["label"], "count": b["n"], "models": sorted(b["models"])} for b in brands]


@router.get("/vehicles/{vehicle_id}")
async def vehicle_detail(vehicle_id: str, db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    vehicle = await db.vehicles.find_one({"_id": to_object_id(vehicle_id, "veículo")})
    if vehicle is None:
        raise HTTPException(404, "Veículo não encontrado")
    observations = [
        o async for o in db.inventory_observations.find({"vehicle_id": vehicle["_id"]}).sort("observed_at", 1).limit(2000)
    ]
    price_history = []
    last_price = object()
    for o in observations:
        if o["kind"] == "nao_encontrado":
            continue
        if o["price"] != last_price:
            price_history.append({"date": o["observed_at"], "price": o["price"], "price_on_request": o["price_on_request"]})
            last_price = o["price"]
    presence = [{"date": o["observed_at"], "kind": o["kind"], "run_id": o["run_id"]} for o in observations]
    links = [l async for l in db.post_vehicle_links.find({"vehicle_id": vehicle["_id"]})]
    company = await db.companies.find_one({"_id": vehicle["company_id"]}, {"name": 1})
    vehicle["company_name"] = (company or {}).get("name")
    vehicle["observed_days"] = observed_days(vehicle["first_seen_at"], vehicle.get("last_seen_at") or utcnow())
    return serialize({
        "vehicle": vehicle,
        "price_history": price_history,
        "presence": presence,
        "observations_count": len(observations),
        "linked_posts": links,
        "notes": [
            "Histórico construído apenas a partir das coletas realizadas por esta plataforma.",
            "'Não encontrado' indica ausência na coleta completa, não venda confirmada.",
        ],
    })


@router.get("/companies/{company_id}/overview")
async def company_inventory(company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                            period: Period = Depends()):
    data = await inventory_overview(db, company["_id"], period.start, period.end, company.get("min_model_stock", 3))
    data["period"] = {"start": period.start, "end": period.end}
    return serialize(data)
