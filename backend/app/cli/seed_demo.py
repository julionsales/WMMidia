"""Dados DEMONSTRATIVOS opcionais (fictícios e identificados).

- Empresas com prefixo "[DEMO]" e `is_demo=true`; snapshots/posts com origem "demo".
- Não interferem em empresas reais e nunca substituem coletas reais com falha.

Uso:
    docker compose run --rm api python -m app.cli.seed_demo           # cria
    docker compose run --rm api python -m app.cli.seed_demo --remove  # remove tudo que é demo
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import timedelta

from bson import ObjectId

from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.db.mongo import create_client, wait_for_mongo

DEMO = [
    ("[DEMO] Loja Exemplo Norte", "demo_loja_norte", 18_400, ["JEEP", "TOYOTA", "HONDA"]),
    ("[DEMO] Loja Exemplo Sul", "demo_loja_sul", 9_150, ["VOLKSWAGEN", "FIAT", "CHEVROLET"]),
    ("[DEMO] Loja Exemplo Premium", "demo_loja_premium", 32_700, ["BMW", "AUDI", "MERCEDES-BENZ"]),
]
MODELS = {
    "JEEP": ["COMPASS", "RENEGADE", "COMMANDER"], "TOYOTA": ["COROLLA", "HILUX", "YARIS"],
    "HONDA": ["HR-V", "CIVIC", "CITY"], "VOLKSWAGEN": ["T-CROSS", "NIVUS", "POLO"],
    "FIAT": ["PULSE", "STRADA", "TORO"], "CHEVROLET": ["TRACKER", "ONIX", "S10"],
    "BMW": ["320I", "X1", "X3"], "AUDI": ["A3", "Q3", "Q5"], "MERCEDES-BENZ": ["C 300", "GLA 200", "GLC 300"],
}
DISPLAY = {"MERCEDES-BENZ": "Mercedes-Benz", "BMW": "BMW"}


async def remove(db) -> None:
    ids = [c["_id"] async for c in db.companies.find({"is_demo": True}, {"_id": 1})]
    profiles = [p["_id"] async for p in db.instagram_profiles.find({"company_id": {"$in": ids}}, {"_id": 1})]
    for coll in ("vehicles", "inventory_observations", "instagram_snapshots", "instagram_posts",
                 "instagram_post_metrics", "collection_runs", "briefings", "post_vehicle_links"):
        await db[coll].delete_many({"company_id": {"$in": ids}})
    await db.instagram_profiles.delete_many({"_id": {"$in": profiles}})
    await db.companies.delete_many({"_id": {"$in": ids}})
    print(f"Removidas {len(ids)} empresas demonstrativas e seus dados.")


async def seed(db) -> None:
    rng = random.Random(42)
    now = utcnow()
    created_ids = []
    for name, username, followers, brands in DEMO:
        if await db.companies.find_one({"name": name}):
            print(f"Já existe: {name}")
            continue
        cid = ObjectId()
        created_ids.append(cid)
        await db.companies.insert_one({
            "_id": cid, "name": name, "name_lower": name.lower(), "slug": username.replace("_", "-"),
            "website": None, "inventory_url": None, "inventory_parser": "auto", "instagram_username": username,
            "segment": "Seminovos", "city": "Cidade Exemplo", "state": "SP",
            "notes": "DADOS FICTÍCIOS para demonstração. Não representam empresa real.",
            "active": True, "inventory_frequency_hours": 0, "instagram_frequency_hours": 0,
            "competitor_ids": [], "min_model_stock": 3, "load_more": False,
            "is_demo": True, "created_at": now, "updated_at": now, "created_by": "seed_demo",
        })
        pid = ObjectId()
        start = now - timedelta(days=60)
        await db.instagram_profiles.insert_one({
            "_id": pid, "username": username, "company_id": cid, "full_name": name, "biography": "Perfil fictício (demo)",
            "created_at": start, "monitoring_started_at": start, "is_private": False, "last_success_at": now,
        })
        count = followers
        snaps = []
        for day in range(0, 61, 3):
            count += rng.randint(-15, 90)
            snaps.append({"profile_id": pid, "company_id": cid, "run_id": None, "collected_at": start + timedelta(days=day),
                          "source": "demo", "status": "success", "followers": count, "following": 300, "media_count": 400 + day // 2,
                          "posts_collected": 0, "posts_requested": 0, "error_code": None, "error_message": None,
                          "notes": ["Dado demonstrativo"], "entered_by": "seed_demo"})
        await db.instagram_snapshots.insert_many(snaps)
        latest = {"followers": count, "following": 300, "media_count": 430, "collected_at": snaps[-1]["collected_at"],
                  "source": "demo", "status": "success"}
        await db.instagram_profiles.update_one({"_id": pid}, {"$set": {"latest": latest}})
        posts, metrics = [], []
        for i in range(24):
            post_id = ObjectId()
            taken = now - timedelta(days=i * 2.3, hours=rng.randint(0, 10))
            fmt = rng.choice(["imagem", "carrossel", "reels", "reels", "video"])
            likes = None if i % 11 == 5 else rng.randint(40, 900) * (2 if fmt == "reels" else 1)
            comments = None if likes is None else rng.randint(0, 60)
            shortcode = f"DEMO{username[-4:].upper()}{i:03d}"
            observed = {"likes": likes, "comments": comments, "likes_hidden": likes is None, "observed_at": now,
                        "followers_at_observation": count}
            posts.append({"_id": post_id, "profile_id": pid, "company_id": cid, "shortcode": shortcode,
                          "url": f"https://www.instagram.com/p/{shortcode}/", "taken_at": taken,
                          "caption": f"[DEMO] Publicação fictícia {i + 1} — {rng.choice(MODELS[brands[0]])}",
                          "format": fmt, "latest_metrics": observed, "first_seen_at": now, "last_seen_at": now, "source": "demo"})
            metrics.append({"post_id": post_id, "profile_id": pid, "company_id": cid, "observed_at": now,
                            "likes": likes, "comments": comments, "likes_hidden": likes is None,
                            "followers_at_observation": count, "source": "demo"})
        await db.instagram_posts.insert_many(posts)
        await db.instagram_post_metrics.insert_many(metrics)

        vehicles, observations = [], []
        for i in range(rng.randint(18, 40)):
            brand = rng.choice(brands)
            model = rng.choice(MODELS[brand])
            vid = ObjectId()
            first = now - timedelta(days=rng.randint(1, 60))
            price = float(rng.randint(60, 450) * 1000)
            missing = i % 9 == 0
            vehicles.append({
                "_id": vid, "company_id": cid, "vehicle_key": f"id:demo-{username}-{i}", "key_type": "source_id",
                "source_id": f"demo-{i}", "brand": brand, "brand_display": DISPLAY.get(brand, brand.title()), "model": model,
                "version": "VERSÃO DEMO", "year_fabrication": 2022, "year_model": 2023, "km": rng.randint(5, 90) * 1000,
                "price": price, "price_on_request": False, "price_text": "", "url": None, "title": f"[DEMO] {brand} {model}",
                "status": "nao_encontrado" if missing else "ativo", "first_seen_at": first,
                "last_seen_at": now - timedelta(days=3) if missing else now, "missing_since": now - timedelta(days=1) if missing else None,
                "times_seen": 5, "price_change_count": 1 if i % 5 == 0 else 0, "first_price": price,
            })
            observations.append({"company_id": cid, "vehicle_id": vid, "run_id": ObjectId(), "observed_at": first, "kind": "novo",
                                 "price": price * (1.05 if i % 5 == 0 else 1), "price_on_request": False, "km": None,
                                 "previous_price": None, "price_changed": False})
            if i % 5 == 0:
                observations.append({"company_id": cid, "vehicle_id": vid, "run_id": ObjectId(), "observed_at": now - timedelta(days=2),
                                     "kind": "presente", "price": price, "price_on_request": False, "km": None,
                                     "previous_price": price * 1.05, "price_changed": True})
        await db.vehicles.insert_many(vehicles)
        await db.inventory_observations.insert_many(observations)
        active = sum(1 for v in vehicles if v["status"] == "ativo")
        await db.companies.update_one({"_id": cid}, {"$set": {
            "inventory_summary": {"active_count": active, "last_success_at": now, "last_complete_at": now, "last_found": active},
            "instagram_summary": {"profile_id": pid, "latest": latest, "last_status": "success", "last_attempt_at": now},
        }})
        print(f"Criada {name} (fictícia)")
    if len(created_ids) > 1:
        for cid in created_ids:
            await db.companies.update_one({"_id": cid}, {"$set": {"competitor_ids": [c for c in created_ids if c != cid]}})


async def main(remove_only: bool) -> None:
    settings = get_settings()
    client = create_client(settings)
    try:
        await wait_for_mongo(client, attempts=10)
        db = client[settings.mongo_db]
        await (remove(db) if remove_only else seed(db))
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dados demonstrativos (fictícios)")
    parser.add_argument("--remove", action="store_true")
    asyncio.run(main(parser.parse_args().remove))
