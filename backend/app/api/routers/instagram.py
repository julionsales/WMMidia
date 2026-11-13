from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.api.deps import Period, current_user, get_company, get_db
from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.models.common import page_payload, serialize, to_object_id
from app.models.schemas import ManualSnapshotIn, PostVehicleLinkIn
from app.services.instagram.service import add_manual_snapshot
from app.services.metrics import instagram as ig
from app.services.metrics.dashboard import instagram_overview

router = APIRouter(prefix="/instagram", tags=["Instagram"])


@router.get("/companies/{company_id}/dashboard")
async def dashboard(company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                    period: Period = Depends()):
    data = await instagram_overview(db, company, period.start, period.end)
    return serialize(data)


@router.get("/companies/{company_id}/snapshots")
async def snapshots(company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200)):
    query = {"company_id": company["_id"]}
    total = await db.instagram_snapshots.count_documents(query)
    cursor = db.instagram_snapshots.find(query).sort("collected_at", -1).skip((page - 1) * size).limit(size)
    return page_payload([s async for s in cursor], total, page, size)


@router.post("/companies/{company_id}/snapshots", status_code=201)
async def manual_snapshot(payload: ManualSnapshotIn, company: dict = Depends(get_company),
                          db: AsyncDatabase = Depends(get_db), user: dict = Depends(current_user)):
    if payload.collected_at > utcnow():
        raise HTTPException(422, "A data do snapshot não pode estar no futuro")
    try:
        doc = await add_manual_snapshot(db, company, payload, user["email"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return serialize(doc)


@router.get("/companies/{company_id}/posts")
async def posts(company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db), period: Period = Depends(),
                page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                sort: str = Query("taken_at", pattern="^(taken_at|interactions)$")):
    settings = get_settings()
    username = company.get("instagram_username")
    profile = await db.instagram_profiles.find_one({"username": username}) if username else None
    if profile is None:
        return page_payload([], 0, page, size)
    snaps = ig.valid_snaps([s async for s in db.instagram_snapshots.find({"profile_id": profile["_id"]})])
    query = {"profile_id": profile["_id"], "taken_at": {"$gte": period.start, "$lte": period.end}}
    raw = [p async for p in db.instagram_posts.find(query).sort("taken_at", -1)]
    enriched = ig.enrich_posts(raw, snaps, settings.instagram_followers_tolerance_days)
    if sort == "interactions":
        enriched.sort(key=lambda p: (p["visible_interactions"] is not None, p["visible_interactions"] or 0), reverse=True)
    items = enriched[(page - 1) * size: page * size]
    links = {}
    async for link in db.post_vehicle_links.find({"post_id": {"$in": [p["_id"] for p in items]}}):
        links.setdefault(link["post_id"], []).append(link)
    for item in items:
        item["vehicle_links"] = links.get(item["_id"], [])
    return page_payload(items, len(enriched), page, size)


@router.get("/posts/{post_id}/metrics")
async def post_metrics(post_id: str, db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    oid = to_object_id(post_id, "publicação")
    post = await db.instagram_posts.find_one({"_id": oid})
    if post is None:
        raise HTTPException(404, "Publicação não encontrada")
    history = [m async for m in db.instagram_post_metrics.find({"post_id": oid}).sort("observed_at", 1)]
    return serialize({"post": post, "history": history})


@router.post("/links", status_code=201)
async def link_post_vehicle(payload: PostVehicleLinkIn, db: AsyncDatabase = Depends(get_db),
                            user: dict = Depends(current_user)):
    """Associação MANUAL entre publicação e anúncio (o sistema não associa automaticamente)."""
    post = await db.instagram_posts.find_one({"_id": to_object_id(payload.post_id, "publicação")})
    vehicle = await db.vehicles.find_one({"_id": to_object_id(payload.vehicle_id, "veículo")})
    if post is None or vehicle is None:
        raise HTTPException(404, "Publicação ou veículo não encontrado")
    if post["company_id"] != vehicle["company_id"]:
        raise HTTPException(422, "Publicação e veículo pertencem a empresas diferentes")
    doc = {
        "post_id": post["_id"], "vehicle_id": vehicle["_id"], "company_id": post["company_id"],
        "note": payload.note, "created_by": user["email"], "created_at": utcnow(), "origin": "manual",
        "post_url": post.get("url"), "vehicle_title": f"{vehicle.get('brand_display')} {vehicle['model']} {vehicle.get('version') or ''}".strip(),
    }
    try:
        res = await db.post_vehicle_links.insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Associação já existe") from exc
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.delete("/links/{link_id}", status_code=204)
async def unlink(link_id: str, db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    res = await db.post_vehicle_links.delete_one({"_id": to_object_id(link_id, "associação")})
    if res.deleted_count == 0:
        raise HTTPException(404, "Associação não encontrada")
