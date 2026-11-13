from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import current_user, get_db
from app.models.common import page_payload, serialize, to_object_id
from app.services.runs import next_scheduled_at

router = APIRouter(prefix="/runs", tags=["Coletas"])


@router.get("")
async def list_runs(
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    company_id: str | None = None,
    source: str | None = Query(None, pattern="^(inventory|instagram)$"),
    status: str | None = None,
    partial: bool | None = None,
    db: AsyncDatabase = Depends(get_db),
    _user: dict = Depends(current_user),
):
    query: dict = {}
    if company_id:
        query["company_id"] = to_object_id(company_id, "empresa")
    if source:
        query["source"] = source
    if status:
        query["status"] = status
    if partial is not None:
        query["partial"] = partial
    total = await db.collection_runs.count_documents(query)
    cursor = db.collection_runs.find(query, {"details.warnings": 0}).sort("created_at", -1).skip((page - 1) * size).limit(size)
    items = [r async for r in cursor]
    company_ids = list({r["company_id"] for r in items})
    companies = {c["_id"]: c async for c in db.companies.find({"_id": {"$in": company_ids}})}
    for run in items:
        company = companies.get(run["company_id"]) or {}
        run["company_name"] = company.get("name")
        run["duration_seconds"] = (
            round((run["finished_at"] - run["started_at"]).total_seconds())
            if run.get("finished_at") and run.get("started_at") else None
        )
    # Próxima coleta programada por empresa/fonte (com base na última execução).
    schedule = []
    async for company in db.companies.find({"active": True} if not company_id else {"_id": query["company_id"]}):
        for src in ("inventory", "instagram"):
            last = await db.collection_runs.find_one({"company_id": company["_id"], "source": src}, sort=[("created_at", -1)])
            nxt = next_scheduled_at(company, src, last)
            if nxt:
                schedule.append({"company_id": company["_id"], "company_name": company["name"], "source": src,
                                 "next_at": nxt, "frequency_hours": company.get(f"{src}_frequency_hours")})
    return page_payload(items, total, page, size, schedule=schedule)


@router.get("/{run_id}")
async def run_detail(run_id: str, db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    run = await db.collection_runs.find_one({"_id": to_object_id(run_id, "execução")})
    if run is None:
        raise HTTPException(404, "Execução não encontrada")
    company = await db.companies.find_one({"_id": run["company_id"]}, {"name": 1})
    run["company_name"] = (company or {}).get("name")
    return serialize(run)
