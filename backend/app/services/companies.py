"""Cadastro de empresas."""

from __future__ import annotations

import re

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.timeutil import utcnow
from app.core.validators import slugify
from app.models.schemas import CompanyIn
from app.services.inventory.parsers import resolve_parser_key


class CompanyError(ValueError):
    pass


def _document(payload: CompanyIn) -> dict:
    data = payload.model_dump()
    data["instagram_username"] = data.pop("instagram")
    data["name_lower"] = data["name"].lower()
    data["competitor_ids"] = [ObjectId(c) for c in data["competitor_ids"] if ObjectId.is_valid(c)]
    if data["inventory_url"]:
        resolve_parser_key(data["inventory_parser"], data["inventory_url"])
    return data


async def _check_competitors(db: AsyncDatabase, ids: list[ObjectId], self_id: ObjectId | None) -> None:
    if self_id is not None and self_id in ids:
        raise CompanyError("Uma empresa não pode ser concorrente de si mesma")
    if ids:
        found = await db.companies.count_documents({"_id": {"$in": ids}})
        if found != len(ids):
            raise CompanyError("Concorrente informado não existe")


async def create_company(db: AsyncDatabase, payload: CompanyIn, user: str) -> dict:
    data = _document(payload)
    await _check_competitors(db, data["competitor_ids"], None)
    now = utcnow()
    base = slugify(data["name"])
    for suffix in range(0, 50):
        slug = base if suffix == 0 else f"{base}-{suffix + 1}"
        doc = {**data, "slug": slug, "created_at": now, "updated_at": now, "created_by": user, "is_demo": False}
        try:
            res = await db.companies.insert_one(doc)
            doc["_id"] = res.inserted_id
            return doc
        except DuplicateKeyError:
            continue
    raise CompanyError("Não foi possível gerar identificador único para a empresa")


async def update_company(db: AsyncDatabase, company_id: ObjectId, payload: CompanyIn, user: str) -> dict | None:
    data = _document(payload)
    await _check_competitors(db, data["competitor_ids"], company_id)
    data.update({"updated_at": utcnow(), "updated_by": user})
    return await db.companies.find_one_and_update(
        {"_id": company_id}, {"$set": data}, return_document=ReturnDocument.AFTER
    )


async def set_competitors(db: AsyncDatabase, company_id: ObjectId, ids: list[str]) -> dict | None:
    oids = [ObjectId(c) for c in dict.fromkeys(ids) if ObjectId.is_valid(c)]
    await _check_competitors(db, oids, company_id)
    return await db.companies.find_one_and_update(
        {"_id": company_id}, {"$set": {"competitor_ids": oids, "updated_at": utcnow()}},
        return_document=ReturnDocument.AFTER,
    )


async def set_active(db: AsyncDatabase, company_id: ObjectId, active: bool, user: str) -> dict | None:
    return await db.companies.find_one_and_update(
        {"_id": company_id},
        {"$set": {"active": active, "updated_at": utcnow(), "updated_by": user}},
        return_document=ReturnDocument.AFTER,
    )


def search_filter(search: str | None, active: bool | None = None, segment: str | None = None,
                  include_demo: bool = True) -> dict:
    query: dict = {}
    if search:
        pattern = re.escape(search.strip().lower())
        query["$or"] = [
            {"name_lower": {"$regex": pattern}},
            {"instagram_username": {"$regex": pattern}},
            {"city": {"$regex": pattern, "$options": "i"}},
        ]
    if active is not None:
        query["active"] = active
    if segment:
        query["segment"] = segment
    if not include_demo:
        query["is_demo"] = {"$ne": True}
    return query
