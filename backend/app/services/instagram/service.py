"""Persistência do monitoramento do Instagram.

- Cada coleta gera um snapshot (sucesso, parcial ou falha) com data, origem e status.
- O "último resultado válido" do perfil (`latest`) só é substituído por coleta com
  número de seguidores disponível; falhas preservam o anterior.
- Publicações são únicas por (perfil, shortcode); métricas de cada observação ficam em
  `instagram_post_metrics` (uma linha por coleta), nunca em arrays crescentes.
- Histórico anterior ao início do monitoramento não é inventado.
"""

from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument, UpdateOne
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import BulkWriteError

from app.core.timeutil import utcnow
from app.services.instagram.providers.base import ProfileFetchResult

VALID_SNAPSHOT_STATUSES = ("success", "partial")


async def ensure_profile(db: AsyncDatabase, company_id: ObjectId, username: str) -> dict:
    now = utcnow()
    return await db.instagram_profiles.find_one_and_update(
        {"username": username},
        {
            "$set": {"company_id": company_id},
            "$setOnInsert": {"username": username, "created_at": now, "monitoring_started_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


async def persist_profile_result(db: AsyncDatabase, company_id: ObjectId, run_id: ObjectId, username: str,
                                 result: ProfileFetchResult, collected_at: datetime | None = None) -> dict:
    collected_at = collected_at or utcnow()
    profile_doc = await ensure_profile(db, company_id, username)
    pid = profile_doc["_id"]
    data = result.profile
    snapshot = {
        "profile_id": pid,
        "company_id": company_id,
        "run_id": run_id,
        "collected_at": collected_at,
        "source": result.source,
        "status": result.status,
        "followers": data.followers if data else None,
        "following": data.following if data else None,
        "media_count": data.media_count if data else None,
        "posts_collected": len(result.posts),
        "posts_requested": result.posts_requested,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "notes": result.notes,
        "entered_by": None,
    }
    await db.instagram_snapshots.update_one(
        {"profile_id": pid, "run_id": run_id}, {"$setOnInsert": snapshot}, upsert=True
    )

    profile_set: dict = {"last_attempt_at": collected_at, "last_status": result.status, "last_error_code": result.error_code}
    if data and result.status in VALID_SNAPSHOT_STATUSES:
        profile_set.update({
            "full_name": data.full_name,
            "biography": data.biography,
            "is_private": data.is_private,
            "external_id": data.external_id,
            "last_success_at": collected_at,
        })
        if data.followers is not None:
            profile_set["latest"] = {
                "followers": data.followers,
                "following": data.following,
                "media_count": data.media_count,
                "collected_at": collected_at,
                "source": result.source,
                "status": result.status,
            }
    await db.instagram_profiles.update_one({"_id": pid}, {"$set": profile_set})

    if result.posts:
        ops = []
        for post in result.posts:
            ops.append(UpdateOne(
                {"profile_id": pid, "shortcode": post.shortcode},
                {
                    "$set": {
                        "company_id": company_id,
                        "url": post.url,
                        "taken_at": post.taken_at,
                        "caption": post.caption,
                        "format": post.format,
                        "external_id": post.external_id,
                        "is_pinned": post.is_pinned,
                        "latest_metrics": {
                            "likes": post.likes,
                            "comments": post.comments,
                            "likes_hidden": post.likes_hidden,
                            "observed_at": collected_at,
                            "followers_at_observation": data.followers if data else None,
                        },
                        "last_seen_at": collected_at,
                    },
                    "$setOnInsert": {"first_seen_at": collected_at, "source": result.source},
                },
                upsert=True,
            ))
        await db.instagram_posts.bulk_write(ops, ordered=False)
        ids = {
            d["shortcode"]: d["_id"]
            async for d in db.instagram_posts.find(
                {"profile_id": pid, "shortcode": {"$in": [p.shortcode for p in result.posts]}}, {"shortcode": 1}
            )
        }
        metrics = [
            {
                "post_id": ids[p.shortcode],
                "profile_id": pid,
                "company_id": company_id,
                "run_id": run_id,
                "observed_at": collected_at,
                "likes": p.likes,
                "comments": p.comments,
                "likes_hidden": p.likes_hidden,
                "followers_at_observation": data.followers if data else None,
                "source": result.source,
            }
            for p in result.posts
            if p.shortcode in ids
        ]
        try:
            await db.instagram_post_metrics.insert_many(metrics, ordered=False)
        except BulkWriteError as exc:
            if any(e.get("code") != 11000 for e in exc.details.get("writeErrors", [])):
                raise

    latest = (await db.instagram_profiles.find_one({"_id": pid}, {"latest": 1})) or {}
    await db.companies.update_one(
        {"_id": company_id},
        {"$set": {
            "instagram_summary.profile_id": pid,
            "instagram_summary.last_attempt_at": collected_at,
            "instagram_summary.last_status": result.status,
            "instagram_summary.latest": latest.get("latest"),
        }},
    )
    return {
        "status": result.status,
        "followers": data.followers if data else None,
        "posts_collected": len(result.posts),
        "error_code": result.error_code,
        "notes": result.notes,
    }


async def add_manual_snapshot(db: AsyncDatabase, company: dict, payload, user_email: str) -> dict:
    username = company.get("instagram_username")
    if not username:
        raise ValueError("Empresa sem perfil do Instagram cadastrado")
    profile = await ensure_profile(db, company["_id"], username)
    doc = {
        "profile_id": profile["_id"],
        "company_id": company["_id"],
        "run_id": None,
        "collected_at": payload.collected_at,
        "source": "manual",
        "status": "success" if payload.followers is not None else "partial",
        "followers": payload.followers,
        "following": payload.following,
        "media_count": payload.media_count,
        "posts_collected": 0,
        "posts_requested": 0,
        "error_code": None,
        "error_message": None,
        "notes": [payload.note],
        "entered_by": user_email,
        "entered_at": utcnow(),
    }
    res = await db.instagram_snapshots.insert_one(doc)
    doc["_id"] = res.inserted_id
    current = profile.get("latest") or {}
    if payload.followers is not None and (not current or current.get("collected_at") is None
                                          or payload.collected_at >= current["collected_at"]):
        latest = {
            "followers": payload.followers, "following": payload.following, "media_count": payload.media_count,
            "collected_at": payload.collected_at, "source": "manual", "status": doc["status"],
        }
        await db.instagram_profiles.update_one({"_id": profile["_id"]}, {"$set": {"latest": latest}})
        await db.companies.update_one({"_id": company["_id"]}, {"$set": {"instagram_summary.latest": latest,
                                                                        "instagram_summary.profile_id": profile["_id"]}})
    return doc
