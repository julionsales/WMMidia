from app.core.validators import normalize_instagram_username
from app.services.inventory.normalize import (
    RawVehicle,
    normalize_and_dedupe,
    normalize_url,
    normalize_vehicle,
    parse_km,
    parse_money,
    parse_years,
)

import pytest


@pytest.mark.parametrize("text,expected", [
    ("R$ 205.900,00", (205900.0, False)),
    ("R$ 93.900", (93900.0, False)),
    ("R$ 1.234.567,89", (1234567.89, False)),
    ("R$ 174990.00000", (174990.0, False)),
    ("R$ Sob Consulta", (None, True)),
    ("Sob consulta", (None, True)),
    ("", (None, False)),
    ("R$ 0,00", (None, False)),
])
def test_parse_money(text, expected):
    assert parse_money(text) == expected


def test_parse_years_and_km():
    assert parse_years("2021/2022") == (2021, 2022)
    assert parse_years("2026 - FREEDOM") == (None, 2026)
    assert parse_years("sem ano") == (None, None)
    assert parse_km("62.000 km") == 62000
    assert parse_km("0 km") == 0
    assert parse_km(None) is None


def test_brand_aliases_and_display():
    v = normalize_vehicle(RawVehicle(brand="Citroën", model="c3", version="1.0", price_text="R$ 68.900,00", source_id="1"))
    assert v.brand == "CITROEN" and v.brand_display == "Citroën" and v.model == "C3"
    v = normalize_vehicle(RawVehicle(brand="MERCEDES", model="GLA 200", source_id="2"))
    assert v.brand == "MERCEDES-BENZ" and v.brand_display == "Mercedes-Benz"


def test_vehicle_key_preference_and_price_independence():
    with_id = normalize_vehicle(RawVehicle(brand="AUDI", model="A3", source_id="5700344", url="https://x.com/a"))
    assert with_id.vehicle_key == "id:5700344" and with_id.key_type == "source_id"
    with_url = normalize_vehicle(RawVehicle(brand="AUDI", model="A3", url="https://x.com/a/?utm_source=ig#top"))
    same_url = normalize_vehicle(RawVehicle(brand="AUDI", model="A3", url="https://X.com/a"))
    assert with_url.key_type == "url" and with_url.vehicle_key == same_url.vehicle_key
    a = normalize_vehicle(RawVehicle(brand="AUDI", model="A3", version="SPORT", year_text="2022", km="10.000 km", price_text="R$ 100.000"))
    b = normalize_vehicle(RawVehicle(brand="AUDI", model="A3", version="SPORT", year_text="2022", km="10.000 km", price_text="R$ 95.000"))
    assert a.key_type == "attributes" and a.vehicle_key == b.vehicle_key  # preço não entra na chave


def test_dedupe_counts_duplicates_and_invalid():
    raws = [
        RawVehicle(brand="AUDI", model="A3", source_id="1"),
        RawVehicle(brand="AUDI", model="A3", source_id="1"),
        RawVehicle(brand="", model=""),
        RawVehicle(brand="BMW", model="X1", source_id="2"),
    ]
    vehicles, duplicates, invalid = normalize_and_dedupe(raws)
    assert [v.vehicle_key for v in vehicles] == ["id:1", "id:2"]
    assert duplicates == 1 and invalid == 1


def test_normalize_url_strips_tracking():
    assert normalize_url("/Veiculo/a/1/detalhes?utm_campaign=x&id=3", "https://Site.com.br/Veiculos") == \
        "https://site.com.br/Veiculo/a/1/detalhes?id=3"
    assert normalize_url("javascript:void(0)") is None


@pytest.mark.parametrize("raw,expected", [
    ("@AvancePremium_", "avancepremium_"),
    ("https://www.instagram.com/azulpremium/?hl=pt", "azulpremium"),
    ("instagram.com/grupo.hazul", "grupo.hazul"),
    ("  perfil_teste ", "perfil_teste"),
    ("", None),
])
def test_instagram_username(raw, expected):
    assert normalize_instagram_username(raw) == expected


@pytest.mark.parametrize("raw", ["https://facebook.com/x", "https://instagram.com/p/ABC123/", "nome inválido", "a..b"])
def test_instagram_username_invalid(raw):
    with pytest.raises(ValueError):
        normalize_instagram_username(raw)
