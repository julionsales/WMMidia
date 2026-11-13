from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import Period, current_user, get_company, get_db
from app.api.routers.inventory import vehicle_filter
from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.core.validators import slugify
from app.services import exports
from app.services.metrics import instagram as ig
from app.services.metrics.inventory import inventory_overview, observed_days

router = APIRouter(prefix="/exports", tags=["Exportações"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_ROWS = 50_000


def _download(content: bytes, media: str, filename: str) -> Response:
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/vehicles.{fmt}")
async def vehicles(
    fmt: str,
    company_id: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    status: str | None = Query("ativo"),
    search: str | None = None,
    db: AsyncDatabase = Depends(get_db),
    _user: dict = Depends(current_user),
):
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(404, "Formato não suportado")
    query = vehicle_filter(company_id, brand, model, year_min, year_max, price_min, price_max, status, search)
    rows = [v async for v in db.vehicles.find(query).sort([("brand", 1), ("model", 1)]).limit(MAX_ROWS)]
    names = {c["_id"]: c["name"] async for c in db.companies.find({}, {"name": 1})}
    now = utcnow()
    for v in rows:
        v["company_name"] = names.get(v["company_id"])
        v["observed_days"] = observed_days(v["first_seen_at"], v.get("last_seen_at") or now)
    stamp = now.strftime("%Y%m%d_%H%M")
    if fmt == "csv":
        return _download(exports.to_csv(rows, exports.VEHICLE_COLUMNS), "text/csv; charset=utf-8", f"estoque_{stamp}.csv")
    sheets = {"Estoque": (rows, exports.VEHICLE_COLUMNS)}
    if company_id:
        company = await db.companies.find_one({"_id": rows[0]["company_id"]}) if rows else None
        if company:
            period_end = now
            overview = await inventory_overview(db, company["_id"], period_end, period_end, company.get("min_model_stock", 3))
            sheets["Ranking Marcas"] = (overview["by_brand"], [("brand", "Marca"), ("count", "Estoque"),
                                                                ("price_min", "Preço mín."), ("price_max", "Preço máx.")])
            sheets["Ranking Modelos"] = (overview["by_model"], [("brand", "Marca"), ("model", "Modelo"), ("count", "Estoque"),
                                                                 ("price_min", "Preço mín."), ("price_max", "Preço máx."),
                                                                 ("km_avg", "Km médio"), ("content_category", "Categoria de conteúdo")])
    content = await asyncio.to_thread(exports.to_xlsx, sheets)
    return _download(content, XLSX, f"estoque_{stamp}.xlsx")


@router.get("/companies/{company_id}/instagram-posts.{fmt}")
async def instagram_posts(fmt: str, company: dict = Depends(get_company), period: Period = Depends(),
                          db: AsyncDatabase = Depends(get_db)):
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(404, "Formato não suportado")
    profile = await db.instagram_profiles.find_one({"username": company.get("instagram_username")}) if company.get("instagram_username") else None
    rows: list[dict] = []
    snapshots: list[dict] = []
    if profile:
        snapshots = [s async for s in db.instagram_snapshots.find({"profile_id": profile["_id"]}).sort("collected_at", 1)]
        snaps = ig.valid_snaps(snapshots)
        raw = [p async for p in db.instagram_posts.find(
            {"profile_id": profile["_id"], "taken_at": {"$gte": period.start, "$lte": period.end}}).sort("taken_at", -1)]
        rows = [exports.flatten_post(p) for p in ig.enrich_posts(raw, snaps, get_settings().instagram_followers_tolerance_days)]
    name = f"instagram_{slugify(company['name'])}_{utcnow():%Y%m%d}"
    if fmt == "csv":
        return _download(exports.to_csv(rows, exports.POST_COLUMNS), "text/csv; charset=utf-8", f"{name}.csv")
    snap_cols = [("collected_at", "Data"), ("source", "Origem"), ("status", "Status"), ("followers", "Seguidores"),
                 ("following", "Seguindo"), ("media_count", "Publicações"), ("error_code", "Erro"), ("entered_by", "Responsável")]
    content = await asyncio.to_thread(exports.to_xlsx, {"Publicações": (rows, exports.POST_COLUMNS),
                                                         "Snapshots": (snapshots, snap_cols)})
    return _download(content, XLSX, f"{name}.xlsx")
