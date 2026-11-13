"""Consultas que alimentam dashboards, visão geral e comparativos."""

from __future__ import annotations

from datetime import datetime, timedelta

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.core.timeutil import ensure_utc, utcnow
from app.services.metrics import instagram as ig
from app.services.metrics.inventory import inventory_overview
from app.services.runs import next_scheduled_at

STALE_FACTOR = 2  # dados "desatualizados" quando a última coleta passou de 2x a frequência


async def instagram_overview(db: AsyncDatabase, company: dict, start: datetime, end: datetime,
                             include_posts: bool = True) -> dict:
    settings = get_settings()
    username = company.get("instagram_username")
    if not username:
        return {"status": "sem_perfil", "message": "Empresa sem perfil do Instagram cadastrado."}
    profile = await db.instagram_profiles.find_one({"username": username})
    if profile is None:
        return {"status": "sem_dados", "username": username, "message": "Nenhuma coleta realizada ainda."}

    pid = profile["_id"]
    snapshots = [s async for s in db.instagram_snapshots.find({"profile_id": pid}).sort("collected_at", 1)]
    snaps = ig.valid_snaps(snapshots)
    growth = ig.follower_growth(snaps, start, end)
    all_posts = [p async for p in db.instagram_posts.find({"profile_id": pid}).sort("taken_at", -1)]
    enriched = ig.enrich_posts(all_posts, snaps, settings.instagram_followers_tolerance_days)
    in_period = [p for p in enriched if start <= ensure_utc(p["taken_at"]) <= end]
    latest = profile.get("latest") or {}
    coverage = ig.sample_coverage(all_posts, start, latest.get("media_count"))
    summary = ig.posts_summary(in_period, start, end, coverage)
    if not all_posts:
        # Nenhuma publicação jamais coletada: contagem é desconhecida, não zero.
        summary.update(count=None, per_week=None, count_is_lower_bound=False)

    last_snapshot = snapshots[-1] if snapshots else None
    warnings: list[str] = []
    if last_snapshot and last_snapshot["status"] == "failed":
        warnings.append(
            f"A coleta mais recente falhou ({last_snapshot.get('error_code') or 'erro'}); "
            "exibindo o último resultado válido."
        )
    if last_snapshot and last_snapshot["status"] == "partial":
        warnings.append("A coleta mais recente foi parcial: " + "; ".join(last_snapshot.get("notes") or []))
    if coverage["partial_sample"]:
        warnings.append(coverage["message"])
    if summary["posts_without_metrics"]:
        warnings.append(
            f"{summary['posts_without_metrics']} publicação(ões) do período sem curtidas/comentários públicos "
            "ficaram fora da interação estimada."
        )
    if growth["status"] == "ok" and growth.get("warning"):
        warnings.append(growth["warning"])

    payload = {
        "status": "ok" if snaps else "sem_dados_validos",
        "username": username,
        "profile": {
            "id": pid,
            "full_name": profile.get("full_name"),
            "biography": profile.get("biography"),
            "is_private": profile.get("is_private"),
            "monitoring_started_at": profile.get("monitoring_started_at"),
            "url": f"https://www.instagram.com/{username}/",
        },
        "latest": latest,
        "last_success_at": profile.get("last_success_at"),
        "last_attempt": {
            "at": last_snapshot["collected_at"] if last_snapshot else None,
            "status": last_snapshot["status"] if last_snapshot else None,
            "error_code": last_snapshot.get("error_code") if last_snapshot else None,
            "source": last_snapshot.get("source") if last_snapshot else None,
        },
        "period": {"start": start, "end": end},
        "growth": growth,
        "series": ig.follower_series(snaps),
        "posts_summary": summary,
        "posts_by_week": ig.posts_by_week(in_period),
        "format_performance": ig.format_performance(in_period),
        "top_posts": ig.top_posts(in_period),
        "warnings": warnings,
        "formula": {
            "name": "Interação pública estimada",
            "expression": "(curtidas + comentários) / seguidores × 100",
            "followers_rule": (
                f"Seguidores do snapshot mais próximo da publicação (±{settings.instagram_followers_tolerance_days} "
                "dias); sem snapshot próximo, seguidores da coleta em que as métricas foram observadas."
            ),
            "disclaimer": "Não é engajamento por alcance. Alcance, salvamentos, compartilhamentos e visitas não são públicos.",
        },
    }
    if include_posts:
        payload["posts"] = in_period
    return payload


def _is_stale(company: dict, source: str, last_success: datetime | None) -> bool:
    hours = company.get(f"{source}_frequency_hours") or 0
    if hours <= 0 or not company.get("active"):
        return False
    if last_success is None:
        return True
    return utcnow() - ensure_utc(last_success) > timedelta(hours=hours * STALE_FACTOR)


async def company_row(db: AsyncDatabase, company: dict, start: datetime, end: datetime) -> dict:
    insta = await instagram_overview(db, company, start, end, include_posts=False) if company.get("instagram_username") else None
    inv = company.get("inventory_summary") or {}
    last_runs = {
        src: await db.collection_runs.find_one({"company_id": company["_id"], "source": src}, sort=[("created_at", -1)])
        for src in ("inventory", "instagram")
    }
    ig_last_success = (insta or {}).get("last_success_at")
    stale = []
    if company.get("inventory_url") and _is_stale(company, "inventory", inv.get("last_success_at")):
        stale.append("estoque")
    if company.get("instagram_username") and _is_stale(company, "instagram", ig_last_success):
        stale.append("instagram")
    growth = (insta or {}).get("growth") or {}
    posts = (insta or {}).get("posts_summary") or {}
    return {
        "id": company["_id"],
        "name": company["name"],
        "slug": company.get("slug"),
        "active": company.get("active", True),
        "is_demo": company.get("is_demo", False),
        "segment": company.get("segment"),
        "city": company.get("city"),
        "state": company.get("state"),
        "inventory_url": company.get("inventory_url"),
        "instagram_username": company.get("instagram_username"),
        "followers": ((insta or {}).get("latest") or {}).get("followers"),
        "followers_at": ((insta or {}).get("latest") or {}).get("collected_at"),
        "growth": growth,
        "posts_in_period": posts.get("count"),
        "posts_partial_sample": (posts.get("coverage") or {}).get("partial_sample"),
        "interaction_median": (posts.get("interaction") or {}).get("median"),
        "interaction_n": (posts.get("interaction") or {}).get("n"),
        "vehicles_active": inv.get("active_count"),
        "inventory_last_success_at": inv.get("last_success_at"),
        "instagram_last_success_at": ig_last_success,
        "last_runs": {
            src: ({"status": r["status"], "created_at": r["created_at"], "finished_at": r.get("finished_at"),
                   "partial": r.get("partial")} if r else None)
            for src, r in last_runs.items()
        },
        "next_runs": {src: next_scheduled_at(company, src, r) for src, r in last_runs.items()},
        "stale": stale,
    }


async def compare_companies(db: AsyncDatabase, companies: list[dict], start: datetime, end: datetime) -> dict:
    rows = []
    for company in companies:
        insta = await instagram_overview(db, company, start, end, include_posts=False)
        inv = await inventory_overview(db, company["_id"], start, end, company.get("min_model_stock", 3))
        summary = insta.get("posts_summary") or {}
        rows.append({
            "id": company["_id"],
            "name": company["name"],
            "instagram_username": company.get("instagram_username"),
            "instagram_status": insta.get("status"),
            "followers": (insta.get("latest") or {}).get("followers"),
            "growth": insta.get("growth"),
            "posts": {
                "count": summary.get("count"),
                "per_week": summary.get("per_week"),
                "partial_sample": (summary.get("coverage") or {}).get("partial_sample"),
            },
            "likes": summary.get("likes"),
            "comments": summary.get("comments"),
            "interaction": summary.get("interaction"),
            "formats": summary.get("formats", []),
            "inventory": {
                "active_count": inv["active_count"],
                "by_brand": inv["by_brand"][:8],
                "price_bands": inv["price_bands"],
                "new_in_period": inv["new_in_period"],
                "missing_in_period": inv["missing_in_period"],
                "last_success_at": inv["summary"].get("last_success_at"),
            },
            "warnings": insta.get("warnings", []),
        })
    return {
        "period": {"start": start, "end": end},
        "rows": rows,
        "notes": [
            "Os números mostram diferenças observadas; não há ranking de 'melhor empresa'.",
            "Crescimento usa as datas reais das coletas de cada perfil; períodos cobertos podem diferir.",
            "Interação pública estimada depende de métricas visíveis e do tamanho da amostra (n).",
            "Estoque reflete os anúncios encontrados nos sites, não vendas.",
        ],
    }


async def global_overview(db: AsyncDatabase, days: int = 7) -> dict:
    since = utcnow() - timedelta(days=days)
    statuses = {}
    async for row in await db.collection_runs.aggregate([
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": {"source": "$source", "status": "$status"}, "n": {"$sum": 1}}},
    ]):
        statuses.setdefault(row["_id"]["source"], {})[row["_id"]["status"]] = row["n"]
    companies_active = await db.companies.count_documents({"active": True})
    companies_total = await db.companies.count_documents({})
    vehicles_active = await db.vehicles.count_documents({"status": "ativo"})
    vehicles_total = await db.vehicles.count_documents({})
    profiles = await db.instagram_profiles.count_documents({})
    profiles_ok = await db.instagram_profiles.count_documents({"latest.followers": {"$ne": None}})
    followers_total = 0
    async for p in db.instagram_profiles.find({"latest.followers": {"$ne": None}}, {"latest.followers": 1}):
        followers_total += p["latest"]["followers"]
    recent_failures = [
        r async for r in db.collection_runs.find({"status": {"$in": ["failed", "abandoned"]}, "created_at": {"$gte": since}})
        .sort("created_at", -1).limit(10)
    ]
    names = {c["_id"]: c["name"] async for c in db.companies.find({"_id": {"$in": [r["company_id"] for r in recent_failures]}}, {"name": 1})}
    return {
        "window_days": days,
        "companies": {"active": companies_active, "total": companies_total},
        "runs": statuses,
        "vehicles": {"active": vehicles_active, "observed_total": vehicles_total},
        "instagram": {"profiles": profiles, "profiles_with_data": profiles_ok, "followers_sum": followers_total},
        "recent_failures": [
            {"id": r["_id"], "company_id": r["company_id"], "company": names.get(r["company_id"]), "source": r["source"],
             "status": r["status"], "created_at": r["created_at"], "error_summary": r.get("error_summary")}
            for r in recent_failures
        ],
    }


def oid_list(values: list[str]) -> list[ObjectId]:
    out = []
    for v in values:
        try:
            out.append(ObjectId(v))
        except Exception:  # noqa: BLE001
            continue
    return out
