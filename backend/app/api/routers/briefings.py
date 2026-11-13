from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import current_user, get_company, get_db
from app.core.timeutil import utcnow
from app.core.validators import slugify
from app.models.common import page_payload, serialize, to_object_id
from app.models.schemas import BriefingIn
from app.services.briefing.builder import create_briefing
from app.services.briefing.docx_export import render_briefing_docx

router = APIRouter(tags=["Briefings"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/companies/{company_id}/briefings", status_code=201)
async def generate(payload: BriefingIn, company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                   user: dict = Depends(current_user)):
    end = utcnow()
    doc = await create_briefing(db, company, end - timedelta(days=payload.period_days), end, user["email"], payload.title)
    return serialize(doc)


@router.get("/companies/{company_id}/briefings")
async def list_for_company(company: dict = Depends(get_company), db: AsyncDatabase = Depends(get_db),
                           page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    query = {"company_id": company["_id"]}
    total = await db.briefings.count_documents(query)
    cursor = (db.briefings.find(query, {"facts": 0, "content": 0}).sort("version", -1)
              .skip((page - 1) * size).limit(size))
    return page_payload([b async for b in cursor], total, page, size)


async def _load(db: AsyncDatabase, briefing_id: str) -> dict:
    doc = await db.briefings.find_one({"_id": to_object_id(briefing_id, "briefing")})
    if doc is None:
        raise HTTPException(404, "Briefing não encontrado")
    return doc


@router.get("/briefings/{briefing_id}")
async def detail(briefing_id: str, db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    return serialize(await _load(db, briefing_id))


@router.get("/briefings/{briefing_id}/docx")
async def docx(briefing_id: str, db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    doc = await _load(db, briefing_id)
    content = await asyncio.to_thread(render_briefing_docx, doc)
    name = f"briefing_{slugify(doc['facts']['company']['name'])}_v{doc['version']}.docx"
    return Response(content, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/briefings/{briefing_id}/json")
async def as_json(briefing_id: str, db: AsyncDatabase = Depends(get_db), _user: dict = Depends(current_user)):
    doc = await _load(db, briefing_id)
    name = f"briefing_{slugify(doc['facts']['company']['name'])}_v{doc['version']}.json"
    return Response(json.dumps(serialize(doc), ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
