"""Montagem e versionamento do briefing.

O briefing salvo contém os dados usados ("facts") já serializados: consultá-lo depois
devolve exatamente o mesmo conteúdo, independentemente de novas coletas.
"""

from __future__ import annotations

from datetime import datetime

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.timeutil import fmt_local, utcnow
from app.models.common import serialize
from app.services.briefing import rules
from app.services.metrics.dashboard import compare_companies, instagram_overview
from app.services.metrics.inventory import inventory_overview

BRIEFING_SCHEMA_VERSION = 1


async def collect_facts(db: AsyncDatabase, company: dict, start: datetime, end: datetime) -> dict:
    inventory = await inventory_overview(db, company["_id"], start, end, company.get("min_model_stock", 3))
    instagram = await instagram_overview(db, company, start, end, include_posts=False)
    competitors = [c async for c in db.companies.find({"_id": {"$in": company.get("competitor_ids", [])}})]
    comparison = await compare_companies(db, [company, *competitors], start, end)
    links = [l async for l in db.post_vehicle_links.find({"company_id": company["_id"]}).limit(50)]
    return serialize({
        "company": {
            "id": company["_id"], "name": company["name"], "website": company.get("website"),
            "inventory_url": company.get("inventory_url"), "instagram_username": company.get("instagram_username"),
            "segment": company.get("segment"), "city": company.get("city"), "state": company.get("state"),
            "min_model_stock": company.get("min_model_stock", 3),
        },
        "period": {"start": start, "end": end, "start_label": fmt_local(start, False), "end_label": fmt_local(end, False)},
        "inventory": {k: inventory[k] for k in (
            "active_count", "observed_total", "by_brand", "by_model", "price_bands", "new_in_period",
            "missing_in_period", "price_changes", "observed_days", "longest_observed", "summary",
        )} | {"by_model": inventory["by_model"][:20], "price_changes": inventory["price_changes"][:20]},
        "instagram": instagram,
        "comparison": comparison,
        "manual_links": links,
    })


async def create_briefing(db: AsyncDatabase, company: dict, start: datetime, end: datetime, user: str,
                          title: str | None = None) -> dict:
    facts = await collect_facts(db, company, start, end)
    content = {
        "suggestions": rules.content_suggestions(facts),
        "hypotheses": rules.test_hypotheses(facts),
        "questions": rules.meeting_questions(facts),
        "data_needed": rules.DATA_NEEDED,
        "limitations": rules.LIMITATIONS,
        "sources": [
            {"name": "Site de estoque", "detail": facts["company"].get("inventory_url"),
             "last_success_at": (facts["inventory"].get("summary") or {}).get("last_success_at")},
            {"name": "Instagram (dados públicos)", "detail": facts["company"].get("instagram_username"),
             "last_success_at": (facts["instagram"] or {}).get("last_success_at")},
        ],
    }
    for _ in range(5):
        last = await db.briefings.find_one({"company_id": company["_id"]}, sort=[("version", -1)], projection={"version": 1})
        version = (last or {}).get("version", 0) + 1
        doc = {
            "company_id": company["_id"],
            "version": version,
            "schema_version": BRIEFING_SCHEMA_VERSION,
            "title": title or f"Briefing {company['name']} — v{version}",
            "created_at": utcnow(),
            "created_by": user,
            "period": {"start": start, "end": end},
            "facts": facts,
            "content": content,
        }
        try:
            res = await db.briefings.insert_one(doc)
            doc["_id"] = res.inserted_id
            return doc
        except DuplicateKeyError:
            continue
    raise RuntimeError("Não foi possível gerar nova versão do briefing")
