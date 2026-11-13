from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import Period, current_user, get_company, get_db
from app.models.common import page_payload, serialize
from app.models.schemas import CompanyIn, CompetitorsIn
from app.services import companies as svc
from app.services import runs
from app.services.inventory.parsers import parser_catalog
from app.services.metrics.dashboard import company_row
from app.worker.celery_app import enqueue_run

router = APIRouter(prefix="/companies", tags=["Empresas"])

SORTABLE = {"name": "name_lower", "created_at": "created_at", "updated_at": "updated_at"}


@router.get("/parsers")
async def list_parsers(_user: dict = Depends(current_user)):
    return parser_catalog()


@router.get("")
async def list_companies(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=80),
    active: bool | None = None,
    segment: str | None = None,
    sort: str = Query("name"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncDatabase = Depends(get_db),
    _user: dict = Depends(current_user),
):
    query = svc.search_filter(search, active, segment)
    total = await db.companies.count_documents(query)
    cursor = (
        db.companies.find(query)
        .sort(SORTABLE.get(sort, "name_lower"), 1 if order == "asc" else -1)
        .skip((page - 1) * size)
        .limit(size)
    )
    return page_payload([c async for c in cursor], total, page, size)


@router.get("/options")
async def company_options(db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    """Lista enxuta para seletores (concorrentes, filtros)."""
    cursor = db.companies.find({}, {"name": 1, "active": 1, "instagram_username": 1, "is_demo": 1}).sort("name_lower", 1)
    return serialize([c async for c in cursor])


@router.post("", status_code=201)
async def create(payload: CompanyIn, db: AsyncDatabase = Depends(get_db), user: dict = Depends(current_user)):
    try:
        return serialize(await svc.create_company(db, payload, user["email"]))
    except (svc.CompanyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{company_id}")
async def detail(company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db), period: Period = Depends()):
    row = await company_row(db, company, period.start, period.end)
    competitors = [c async for c in db.companies.find({"_id": {"$in": company.get("competitor_ids", [])}}, {"name": 1})]
    return serialize({**company, "overview": row, "competitors": competitors,
                      "period": {"start": period.start, "end": period.end}})


@router.put("/{company_id}")
async def update(payload: CompanyIn, company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                 user: dict = Depends(current_user)):
    try:
        updated = await svc.update_company(db, company["_id"], payload, user["email"])
    except (svc.CompanyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return serialize(updated)


@router.put("/{company_id}/competitors")
async def competitors(payload: CompetitorsIn, company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db)):
    try:
        return serialize(await svc.set_competitors(db, company["_id"], payload.competitor_ids))
    except svc.CompanyError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{company_id}/deactivate")
async def deactivate(company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                     user: dict = Depends(current_user)):
    return serialize(await svc.set_active(db, company["_id"], False, user["email"]))


@router.post("/{company_id}/activate")
async def activate(company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                   user: dict = Depends(current_user)):
    return serialize(await svc.set_active(db, company["_id"], True, user["email"]))


@router.post("/{company_id}/collect/{source}", status_code=202)
async def collect(source: str, company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                  user: dict = Depends(current_user)):
    """Solicita coleta. A API apenas registra e enfileira; o worker executa."""
    if source not in ("inventory", "instagram"):
        raise HTTPException(404, "Fonte desconhecida")
    if source == "inventory" and not company.get("inventory_url"):
        raise HTTPException(422, "Empresa sem URL de estoque")
    if source == "instagram" and not company.get("instagram_username"):
        raise HTTPException(422, "Empresa sem perfil do Instagram")
    if not company.get("active", True):
        raise HTTPException(409, "Empresa inativa")
    run, created = await runs.request_run(db, company["_id"], source, "manual", user["email"])
    if created:
        try:
            await asyncio.to_thread(enqueue_run, run)
        except Exception as exc:  # noqa: BLE001 - broker indisponível
            await runs.finish_run(db, run["_id"], "failed", error_summary="Fila indisponível; tente novamente",
                                  error_code="broker")
            raise HTTPException(503, "Fila de tarefas indisponível no momento") from exc
    return serialize({
        "run_id": run["_id"],
        "task_id": str(run["_id"]),
        "status": run["status"],
        "created": created,
        "message": "Coleta enfileirada" if created else "Já existe uma coleta ativa para esta empresa e fonte",
    })


@router.get("/{company_id}/runs")
async def company_runs(company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                       page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    query = {"company_id": company["_id"]}
    total = await db.collection_runs.count_documents(query)
    cursor = db.collection_runs.find(query).sort("created_at", -1).skip((page - 1) * size).limit(size)
    return page_payload([r async for r in cursor], total, page, size)
