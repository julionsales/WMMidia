"""Indicadores do Instagram (funções puras, sem acesso ao banco).

Interação pública estimada (por publicação):
    (curtidas + comentários) / seguidores × 100
- Seguidores: snapshot válido mais próximo da data da publicação, dentro de
  ±INSTAGRAM_FOLLOWERS_TOLERANCE_DAYS. Sem snapshot próximo, usa-se o número de
  seguidores da coleta em que as métricas foram observadas (e isso é informado).
- Publicações sem curtidas OU sem comentários disponíveis ficam fora do cálculo
  (não são tratadas como zero). O tamanho da amostra é sempre informado.
- NÃO é engajamento por alcance: alcance não é público.

Crescimento de seguidores:
- Usa somente snapshots reais (sucesso/parcial com seguidores disponíveis).
- Base: último snapshot até o início do período; na falta, o primeiro dentro do período.
- Fim: último snapshot até o fim do período.
- Menos de dois snapshots distintos => "historico_insuficiente" (nunca crescimento zero).
- As datas reais usadas e a cobertura do período são devolvidas para exibição.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Iterable

from app.core.timeutil import SAO_PAULO, ensure_utc

MIN_SPAN = timedelta(hours=20)  # comparações com menos de ~1 dia entre coletas não são informativas


@dataclass(frozen=True)
class Snap:
    at: datetime
    followers: int


def valid_snaps(snapshots: Iterable[dict]) -> list[Snap]:
    out = [
        Snap(ensure_utc(s["collected_at"]), int(s["followers"]))
        for s in snapshots
        if s.get("status") in ("success", "partial") and s.get("followers") is not None
    ]
    return sorted(out, key=lambda s: s.at)


def follower_growth(snaps: list[Snap], start: datetime, end: datetime, min_coverage: float = 0.0) -> dict:
    start, end = ensure_utc(start), ensure_utc(end)
    requested_days = round((end - start).total_seconds() / 86400, 1)
    before = [s for s in snaps if s.at <= start]
    within = [s for s in snaps if start < s.at <= end]
    base = before[-1] if before else (within[0] if within else None)
    final = within[-1] if within else None
    if base is None or final is None or final.at - base.at < MIN_SPAN:
        return {
            "status": "historico_insuficiente",
            "message": "Histórico insuficiente: são necessárias ao menos duas coletas no período, "
                       "com pelo menos um dia de intervalo.",
            "requested_days": requested_days,
            "snapshots_in_period": len(within),
        }
    covered_start = max(base.at, start)
    span_days = round((final.at - base.at).total_seconds() / 86400, 1)
    coverage = min(1.0, (final.at - covered_start).total_seconds() / max((end - start).total_seconds(), 1))
    absolute = final.followers - base.followers
    pct = round(absolute / base.followers * 100, 2) if base.followers else None
    result = {
        "status": "ok",
        "start": {"date": base.at.isoformat(), "followers": base.followers},
        "end": {"date": final.at.isoformat(), "followers": final.followers},
        "absolute": absolute,
        "percent": pct,
        "span_days": span_days,
        "requested_days": requested_days,
        "coverage_ratio": round(coverage, 2),
        "snapshots_in_period": len(within),
        "baseline_before_period": bool(before),
    }
    if coverage < 0.8:
        result["warning"] = (
            f"Comparação cobre {span_days} dia(s) entre coletas reais, não os {requested_days} dias pedidos."
        )
    if coverage < min_coverage:
        result["status"] = "historico_insuficiente"
        result["message"] = "Cobertura do período abaixo do mínimo para comparação."
    return result


def follower_series(snaps: list[Snap]) -> list[dict]:
    return [{"date": s.at.isoformat(), "followers": s.followers} for s in snaps]


def followers_for_post(taken_at: datetime, snaps: list[Snap], tolerance_days: int,
                       fallback_followers: int | None, fallback_at: datetime | None) -> dict | None:
    taken_at = ensure_utc(taken_at)
    tol = timedelta(days=tolerance_days)
    near = [s for s in snaps if abs(s.at - taken_at) <= tol]
    if near:
        best = min(near, key=lambda s: abs(s.at - taken_at))
        return {"followers": best.followers, "date": best.at.isoformat(), "basis": "snapshot_proximo"}
    if fallback_followers:
        return {
            "followers": fallback_followers,
            "date": ensure_utc(fallback_at).isoformat() if fallback_at else None,
            "basis": "seguidores_da_coleta",
        }
    return None


def post_interaction(likes: int | None, comments: int | None, followers_info: dict | None) -> dict:
    if likes is None or comments is None:
        return {"value": None, "reason": "metricas_indisponiveis"}
    if not followers_info or not followers_info.get("followers"):
        return {"value": None, "reason": "seguidores_indisponiveis"}
    value = (likes + comments) / followers_info["followers"] * 100
    return {"value": round(value, 3), **followers_info}


def enrich_posts(posts: list[dict], snaps: list[Snap], tolerance_days: int) -> list[dict]:
    out = []
    for post in posts:
        metrics = post.get("latest_metrics") or {}
        info = followers_for_post(
            post["taken_at"], snaps, tolerance_days,
            metrics.get("followers_at_observation"), metrics.get("observed_at"),
        )
        likes, comments = metrics.get("likes"), metrics.get("comments")
        out.append({
            **post,
            "likes": likes,
            "comments": comments,
            "visible_interactions": likes + comments if likes is not None and comments is not None else None,
            "interaction": post_interaction(likes, comments, info),
        })
    return out


def _stats(values: list[float | int]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None}
    return {"n": len(values), "mean": round(mean(values), 2), "median": round(median(values), 2)}


def sample_coverage(posts_all: list[dict], start: datetime, media_count: int | None) -> dict:
    """Indica se os posts conhecidos cobrem todo o período (frequência confiável).

    Publicações fixadas são ignoradas aqui: aparecem no topo mesmo sendo antigas e
    dariam a falsa impressão de que a amostra alcança o início do período.
    """
    start = ensure_utc(start)
    known = len(posts_all)
    oldest = min((ensure_utc(p["taken_at"]) for p in posts_all if not p.get("is_pinned")), default=None)
    covers = (oldest is not None and oldest <= start) or (media_count is not None and known >= media_count)
    return {
        "known_posts": known,
        "profile_media_count": media_count,
        "oldest_known_post": oldest.isoformat() if oldest else None,
        "partial_sample": not covers,
        "message": None if covers else (
            "Frequência calculada com amostra parcial: a coleta obtém apenas as publicações mais recentes "
            "e não alcança o início do período."
        ),
    }


def posts_summary(posts_period: list[dict], start: datetime, end: datetime, coverage: dict) -> dict:
    days = max((ensure_utc(end) - ensure_utc(start)).total_seconds() / 86400, 1)
    likes = [p["likes"] for p in posts_period if p.get("likes") is not None]
    comments = [p["comments"] for p in posts_period if p.get("comments") is not None]
    interactions = [p["interaction"]["value"] for p in posts_period if p["interaction"].get("value") is not None]
    formats = Counter(p.get("format") or "desconhecido" for p in posts_period)
    return {
        "count": len(posts_period),
        "count_is_lower_bound": coverage["partial_sample"],
        "per_week": round(len(posts_period) / days * 7, 2),
        "likes": _stats(likes),
        "comments": _stats(comments),
        "interaction": _stats(interactions),
        "posts_without_metrics": len(posts_period) - len(interactions),
        "formats": [{"format": k, "count": v} for k, v in formats.most_common()],
        "coverage": coverage,
    }


def posts_by_week(posts: list[dict]) -> list[dict]:
    buckets: Counter = Counter()
    for post in posts:
        local = ensure_utc(post["taken_at"]).astimezone(SAO_PAULO)
        monday = (local - timedelta(days=local.weekday())).date()
        buckets[monday.isoformat()] += 1
    return [{"week_start": k, "count": v} for k, v in sorted(buckets.items())]


def top_posts(posts: list[dict], limit: int = 5) -> list[dict]:
    ranked = [p for p in posts if p.get("visible_interactions") is not None]
    return sorted(ranked, key=lambda p: p["visible_interactions"], reverse=True)[:limit]


def format_performance(posts: list[dict]) -> list[dict]:
    groups: dict[str, list[float]] = {}
    for post in posts:
        value = post["interaction"].get("value")
        if value is not None:
            groups.setdefault(post.get("format") or "desconhecido", []).append(value)
    return [{"format": fmt, **_stats(vals)} for fmt, vals in sorted(groups.items())]
