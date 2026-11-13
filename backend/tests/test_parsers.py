from types import SimpleNamespace

from app.services.inventory.normalize import normalize_and_dedupe
from app.services.inventory.parsers import resolve_parser_key
from app.services.inventory.parsers.avance import AvanceParser
from app.services.inventory.parsers.azul import parse_azul_html
from app.services.inventory.parsers.hazul import parse_hazul_html

from tests.conftest import FakeHttp


def test_azul_parser_uses_card_structure(fixture):
    result = parse_azul_html(fixture("azul.html"), "https://azulpremium.com.br/Veiculos")
    vehicles, _, _ = normalize_and_dedupe(result.vehicles, "https://azulpremium.com.br/Veiculos")
    assert result.declared_total == 4 and len(vehicles) == 4
    by_brand = {v.brand: v for v in vehicles}
    # Marcas fora da lista fixa do script original continuam sendo extraídas.
    assert {"OMODA", "TROLLER", "LAND ROVER", "AUDI"} == set(by_brand)
    audi = by_brand["AUDI"]
    assert (audi.model, audi.version, audi.year_fabrication, audi.year_model, audi.km, audi.price) == \
        ("A3", "2.0 40 TFSI SEDAN", 2021, 2022, 62000, 205900.0)
    assert audi.vehicle_key == "id:5700344"
    assert audi.url == "https://azulpremium.com.br/Veiculo/a3-2.0-sedan-2022/5700344/detalhes"
    defender = by_brand["LAND ROVER"]
    assert defender.price is None and defender.price_on_request is True



def test_azul_parser_reads_newer_autocerto_layout(fixture):
    url = "https://gilcar.com.br/Veiculos"
    result = parse_azul_html(fixture("autocerto_novo.html"), url)
    vehicles, _, _ = normalize_and_dedupe(result.vehicles, url)
    assert result.declared_total == 2 and len(vehicles) == 2
    by_brand = {v.brand: v for v in vehicles}
    x1 = by_brand["BMW"]
    assert (x1.model, x1.version, x1.year_fabrication, x1.year_model, x1.km, x1.price) ==         ("X1", "2.0 16V TURBO GASOLINA SDRIVE20I M SPORT STEPTRONIC", 2024, 2025, 21715, 305889.0)
    assert x1.vehicle_key == "id:5660068"
    dolphin = by_brand["BYD"]
    assert dolphin.model == "DOLPHIN" and dolphin.km == 0 and dolphin.year_model == 2027

def test_hazul_parser_handles_citroen_and_jsonld_models(fixture):
    result, next_pages = parse_hazul_html(fixture("hazul.html"), "https://www.grupohazul.com.br/x/estoque/seminovos")
    vehicles, _, _ = normalize_and_dedupe(result.vehicles)
    assert result.declared_total == 3 and len(vehicles) == 3 and next_pages == []
    cactus = next(v for v in vehicles if v.source_id == "15742551")
    assert cactus.brand == "CITROEN" and cactus.model == "C4 CACTUS" and cactus.version == "1.6 THP FLEX SHINE PACK EAT6"
    assert cactus.km == 45061 and cactus.year_model == 2024 and cactus.price == 97900.0
    kicks = next(v for v in vehicles if v.source_id == "15749939")
    assert kicks.url == "https://www.grupohazul.com.br/x/estoque/seminovos/kicks-8149012"
    sprinter = next(v for v in vehicles if v.brand == "MERCEDES-BENZ")
    assert sprinter.model == "SPRINTER"  # sem JSON-LD: primeira palavra


def test_avance_parser_paginates_until_declared_total(fixture):
    endpoint = "https://avancepremium.com.br/wp-admin/admin-ajax.php"
    http = FakeHttp({f"{endpoint}#1": fixture("avance_p1.html"), f"{endpoint}#2": fixture("avance_p2.html")})
    result = AvanceParser().collect("https://avancepremium.com.br/estoque/", SimpleNamespace(http=http, browser=None), {"max_pages": 10})
    vehicles, _, _ = normalize_and_dedupe(result.vehicles)
    assert result.declared_total == 3 and len(vehicles) == 3 and result.pages_fetched == 2
    strada = next(v for v in vehicles if v.model == "STRADA")
    assert (strada.brand, strada.version, strada.year_model, strada.km, strada.price, strada.source_id) == \
        ("FIAT", "FREEDOM 1.3 FLEX 8V CS PLUS", 2026, 11000, 93900.0, "101045")


def test_avance_parser_respects_page_limit(fixture):
    endpoint = "https://avancepremium.com.br/wp-admin/admin-ajax.php"
    http = FakeHttp({f"{endpoint}#1": fixture("avance_p1.html")})
    result = AvanceParser().collect("https://avancepremium.com.br/estoque/", SimpleNamespace(http=http, browser=None), {"max_pages": 1})
    assert result.reached_end is False and len(result.vehicles) == 2


def test_parser_resolution_by_domain():
    assert resolve_parser_key("auto", "https://www.azulpremium.com.br/Veiculos") == "azul"
    assert resolve_parser_key("auto", "https://avancepremium.com.br/estoque/") == "avance"
    assert resolve_parser_key("auto", "https://outraloja.com.br/estoque") == "generic"
    assert resolve_parser_key("playwright", "https://avancepremium.com.br") == "playwright"
