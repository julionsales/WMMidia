from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import Period, current_user, get_db
from app.models.common import page_payload, serialize
from app.services.companies import search_filter
from app.services.metrics.dashboard import company_row, compare_companies, global_overview, oid_list

router = APIRouter(tags=["Painéis"])

SORT_KEYS = {
    "name": lambda r: (r["name"] or "").lower(),
    "followers": lambda r: r["followers"],
    "growth": lambda r: (r["growth"] or {}).get("percent") if (r["growth"] or {}).get("status") == "ok" else None,
    "posts": lambda r: r["posts_in_period"],
    "interaction": lambda r: r["interaction_median"],
    "vehicles": lambda r: r["vehicles_active"],
    "last_collection": lambda r: max(
        [d for d in (r["inventory_last_success_at"], r["instagram_last_success_at"]) if d] or [None], default=None
    ),
}


@router.get("/dashboard/overview")
async def overview(days: int = Query(7, ge=1, le=90), db: AsyncDatabase = Depends(get_db),
                   _user: dict = Depends(current_user)):
    return serialize(await global_overview(db, days))


@router.get("/dashboard/companies")
async def companies_table(
    period: Period = Depends(),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, max_length=80),
    active: bool | None = None,
    segment: str | None = None,
    stale_only: bool = False,
    sort: str = Query("name"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncDatabase = Depends(get_db),
    _user: dict = Depends(current_user),
):
    """Tabela da visão geral com busca, filtros, ordenação e paginação no servidor.

    Indicadores dependentes do período são calculados no servidor para o conjunto
    filtrado (limitado a 500 empresas) antes de ordenar e paginar.
    """
    query = search_filter(search, active, segment)
    companies = [c async for c in db.companies.find(query).limit(500)]
    rows = [await company_row(db, c, period.start, period.end) for c in companies]
    if stale_only:
        rows = [r for r in rows if r["stale"]]
    key = SORT_KEYS.get(sort, SORT_KEYS["name"])
    present = [r for r in rows if key(r) is not None]
    missing = [r for r in rows if key(r) is None]
    present.sort(key=key, reverse=order == "desc")
    ordered = present + missing  # sem dado sempre ao final, sem virar zero
    total = len(ordered)
    items = ordered[(page - 1) * size: page * size]
    return page_payload(items, total, page, size, period={"start": period.start, "end": period.end, "days": period.days})


@router.get("/compare")
async def compare(ids: list[str] = Query(..., min_length=1, max_length=8), period: Period = Depends(),
                  db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    oids = oid_list(ids)
    if not oids:
        raise HTTPException(422, "Selecione ao menos uma empresa")
    companies = [c async for c in db.companies.find({"_id": {"$in": oids}})]
    order = {oid: i for i, oid in enumerate(oids)}
    companies.sort(key=lambda c: order.get(c["_id"], 99))
    return serialize(await compare_companies(db, companies, period.start, period.end))
