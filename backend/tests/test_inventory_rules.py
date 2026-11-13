from datetime import datetime, timezone

from bson import ObjectId

from app.services.inventory.normalize import RawVehicle, normalize_vehicle
from app.services.inventory.service import assess_completeness, plan_vehicle_upsert

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def test_complete_when_declared_total_matches():
    check = assess_completeness(102, 102, True, 0, previous_active=100, min_ratio=0.5)
    assert check.complete and check.reasons == []


def test_partial_when_fewer_than_declared():
    check = assess_completeness(100, 102, True, 0, previous_active=100, min_ratio=0.5)
    assert not check.complete and "100 de 102" in check.reasons[0]


def test_partial_on_failed_pages_or_page_limit():
    assert not assess_completeness(40, None, True, 1, 40, 0.5).complete
    assert not assess_completeness(40, None, False, 0, 40, 0.5).complete


def test_empty_collection_is_never_complete():
    check = assess_completeness(0, None, True, 0, previous_active=80, min_ratio=0.5)
    assert not check.complete


def test_sudden_drop_without_declared_total_is_partial():
    assert not assess_completeness(10, None, True, 0, previous_active=80, min_ratio=0.5).complete
    # Com total anunciado batendo, a queda é real e a coleta é completa.
    assert assess_completeness(10, 10, True, 0, previous_active=80, min_ratio=0.5).complete


def _vehicle(price="R$ 100.000"):
    return normalize_vehicle(RawVehicle(brand="AUDI", model="A3", source_id="1", price_text=price))


def test_plan_new_vehicle():
    run = ObjectId()
    set_fields, on_insert, obs = plan_vehicle_upsert(None, _vehicle(), NOW, run)
    assert obs["kind"] == "novo" and on_insert["first_seen_at"] == NOW and set_fields["status"] == "ativo"


def test_plan_price_change_and_reappearance():
    run = ObjectId()
    existing = {"price": 105000.0, "status": "nao_encontrado", "last_seen_run_id": ObjectId(), "price_change_count": 2,
                "first_seen_at": NOW, "first_price": 110000.0}
    set_fields, on_insert, obs = plan_vehicle_upsert(existing, _vehicle(), NOW, run)
    assert obs["kind"] == "reapareceu" and obs["price_changed"] and obs["previous_price"] == 105000.0
    assert set_fields["price_change_count"] == 3 and set_fields["missing_since"] is None
    assert on_insert == {}


def test_plan_same_run_is_idempotent():
    run = ObjectId()
    existing = {"price": 105000.0, "status": "ativo", "last_seen_run_id": run, "first_seen_at": NOW}
    _, _, obs = plan_vehicle_upsert(existing, _vehicle(), NOW, run)
    assert obs["price_changed"] is False  # reprocessar a mesma execução não duplica alteração


def test_price_on_request_does_not_count_as_change():
    existing = {"price": 105000.0, "status": "ativo", "last_seen_run_id": ObjectId(), "first_seen_at": NOW}
    _, _, obs = plan_vehicle_upsert(existing, _vehicle("Sob consulta"), NOW, ObjectId())
    assert obs["price_changed"] is False and obs["price_on_request"] is True
