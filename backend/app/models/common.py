"""Serialização consistente de documentos MongoDB para a API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from app.core.timeutil import ensure_utc


def to_object_id(value: str | ObjectId, label: str = "identificador") -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"{label} inválido") from exc


def serialize(value: Any) -> Any:
    """ObjectId -> str, `_id` -> `id`, datas sempre em UTC ISO-8601."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out["id" if key == "_id" else key] = serialize(item)
        return out
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    return value


def page_payload(items: list[Any], total: int, page: int, size: int, **extra: Any) -> dict:
    return {"items": serialize(items), "total": total, "page": page, "size": size, **serialize(extra)}
