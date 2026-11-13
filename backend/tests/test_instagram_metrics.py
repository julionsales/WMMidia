from datetime import datetime, timedelta, timezone

from app.services.metrics import instagram as ig

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def snap(day, followers, status="success"):
    return {"collected_at": T0 + timedelta(days=day), "followers": followers, "status": status}


def test_insufficient_history_with_no_or_single_snapshot():
    assert ig.follower_growth([], T0, T0 + timedelta(days=30))["status"] == "historico_insuficiente"
    one = ig.valid_snaps([snap(5, 1000)])
    result = ig.follower_growth(one, T0, T0 + timedelta(days=30))
    assert result["status"] == "historico_insuficiente" and "absolute" not in result  # nunca vira zero


def test_failed_and_unavailable_snapshots_are_ignored():
    snaps = ig.valid_snaps([snap(1, 1000), snap(10, None), snap(20, 5000, "failed")])
    assert [s.followers for s in snaps] == [1000]


def test_growth_uses_real_snapshot_dates():
    snaps = ig.valid_snaps([snap(0, 1000), snap(12, 1100), snap(25, 1150)])
    result = ig.follower_growth(snaps, T0, T0 + timedelta(days=30))
    assert result["status"] == "ok"
    assert result["absolute"] == 150 and result["percent"] == 15.0
    assert result["start"]["date"] == (T0).isoformat() and result["end"]["date"] == (T0 + timedelta(days=25)).isoformat()
    assert result["span_days"] == 25.0 and result["requested_days"] == 30.0


def test_growth_warns_when_coverage_is_short():
    snaps = ig.valid_snaps([snap(20, 1000), snap(28, 1010)])
    result = ig.follower_growth(snaps, T0, T0 + timedelta(days=30))
    assert result["status"] == "ok" and result["coverage_ratio"] < 0.8 and "warning" in result
    assert result["baseline_before_period"] is False


def test_growth_baseline_before_period():
    snaps = ig.valid_snaps([snap(-3, 900), snap(29, 990)])
    result = ig.follower_growth(snaps, T0, T0 + timedelta(days=30))
    assert result["start"]["followers"] == 900 and result["baseline_before_period"] is True


def _post(day, likes, comments, fmt="imagem", followers_obs=2000):
    return {"taken_at": T0 + timedelta(days=day), "format": fmt,
            "latest_metrics": {"likes": likes, "comments": comments, "observed_at": T0 + timedelta(days=40),
                               "followers_at_observation": followers_obs}}


def test_interaction_uses_nearest_snapshot_or_reports_fallback():
    snaps = ig.valid_snaps([snap(10, 1000)])
    near, far = ig.enrich_posts([_post(11, 90, 10), _post(25, 90, 10)], snaps, tolerance_days=3)
    assert near["interaction"]["value"] == 10.0 and near["interaction"]["basis"] == "snapshot_proximo"
    assert far["interaction"]["value"] == 5.0 and far["interaction"]["basis"] == "seguidores_da_coleta"


def test_unavailable_metrics_are_excluded_not_zero():
    snaps = ig.valid_snaps([snap(10, 1000)])
    posts = ig.enrich_posts([_post(10, 100, 0), _post(11, None, 5), _post(12, 0, 0)], snaps, 3)
    assert posts[1]["interaction"]["value"] is None and posts[1]["visible_interactions"] is None
    assert posts[2]["interaction"]["value"] == 0.0  # zero real continua zero
    coverage = {"partial_sample": False, "message": None}
    summary = ig.posts_summary(posts, T0, T0 + timedelta(days=30), coverage)
    assert summary["interaction"]["n"] == 2 and summary["likes"]["n"] == 2
    assert summary["posts_without_metrics"] == 1
    assert summary["likes"]["mean"] == 50.0


def test_sample_coverage_flags_partial_frequency():
    posts = [{"taken_at": T0 + timedelta(days=d)} for d in (20, 25, 29)]
    partial = ig.sample_coverage(posts, T0, media_count=500)
    assert partial["partial_sample"] is True and partial["message"]
    full = ig.sample_coverage(posts + [{"taken_at": T0 - timedelta(days=1)}], T0, media_count=500)
    assert full["partial_sample"] is False
    all_known = ig.sample_coverage(posts, T0, media_count=3)
    assert all_known["partial_sample"] is False


def test_top_posts_and_formats():
    snaps = ig.valid_snaps([snap(10, 1000)])
    posts = ig.enrich_posts([_post(10, 10, 1, "reels"), _post(10, 50, 5, "imagem"), _post(10, None, 1, "reels")], snaps, 3)
    assert [p["visible_interactions"] for p in ig.top_posts(posts)] == [55, 11]
    perf = {f["format"]: f["n"] for f in ig.format_performance(posts)}
    assert perf == {"imagem": 1, "reels": 1}


def test_pinned_posts_do_not_make_sample_look_complete():
    recent = [{"taken_at": T0 + timedelta(days=d)} for d in (20, 25)]
    pinned_old = {"taken_at": T0 - timedelta(days=300), "is_pinned": True}
    assert ig.sample_coverage(recent + [pinned_old], T0, media_count=None)["partial_sample"] is True


def test_snapshots_minutes_apart_are_insufficient():
    snaps = ig.valid_snaps([snap(10, 1000), {"collected_at": T0 + timedelta(days=10, minutes=5), "followers": 1000, "status": "success"}])
    assert ig.follower_growth(snaps, T0, T0 + timedelta(days=30))["status"] == "historico_insuficiente"


def test_pinned_inferred_from_feed_order():
    from app.services.instagram.providers.base import PostData
    from app.services.instagram.providers.instaloader_provider import mark_pinned_by_order

    def p(code, day):
        return PostData(shortcode=code, url="", taken_at=T0 + timedelta(days=day))

    posts = [p("old_pinned", -300), p("new1", 20), p("new2", 18), p("new3", 10)]
    mark_pinned_by_order(posts)
    assert [x.is_pinned for x in posts] == [True, False, False, False]
