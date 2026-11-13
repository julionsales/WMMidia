"""Normalização e deduplicação de anúncios de veículos.

Chave estável (`vehicle_key`), em ordem de preferência:
1. `id:<identificador da origem>` — ID do anúncio extraído do site (mais confiável);
2. `url:<hash da URL normalizada>` — quando não há ID mas há link do anúncio;
3. `attr:<hash de marca|modelo|versão|ano modelo|km>` — último recurso.

Limitações documentadas da chave `attr`: se a loja editar versão/quilometragem, o
anúncio passa a ser tratado como novo (e o antigo como não encontrado); dois veículos
idênticos sem link nem ID colapsam em um só (o descarte é contado em `duplicates`).
Preço NUNCA entra na chave, para que alterações de preço sejam rastreadas.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

PRICE_RE = re.compile(r"R\$\s*(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2})?|R\$\s*Sob\s+Consulta|Sob\s+consulta", re.I)
YEAR_PAIR_RE = re.compile(r"\b((?:19|20)\d{2})\s*/\s*((?:19|20)\d{2})\b")
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
KM_RE = re.compile(r"\b(\d{1,3}(?:\.\d{3})+|\d+)\s*km\b", re.I)

BRAND_ALIASES = {
    "MERCEDES": "MERCEDES-BENZ",
    "MERCEDES BENZ": "MERCEDES-BENZ",
    "MB": "MERCEDES-BENZ",
    "VW": "VOLKSWAGEN",
    "VW - VOLKSWAGEN": "VOLKSWAGEN",
    "GM": "CHEVROLET",
    "GM - CHEVROLET": "CHEVROLET",
    "CAOA CHERY": "CHERY",
    "CAOA CHERY/CHERY": "CHERY",
    "LAND-ROVER": "LAND ROVER",
    "CITROEN": "CITROEN",
}
BRAND_DISPLAY = {
    "BMW": "BMW", "BYD": "BYD", "GWM": "GWM", "RAM": "RAM", "MINI": "MINI", "JAC": "JAC",
    "MERCEDES-BENZ": "Mercedes-Benz", "LAND ROVER": "Land Rover", "CITROEN": "Citroën",
    "ALFA ROMEO": "Alfa Romeo", "ROLLS-ROYCE": "Rolls-Royce", "ASTON MARTIN": "Aston Martin",
}
# Marcas conhecidas: usadas apenas pelo parser genérico para separar marca do título.
KNOWN_BRANDS = sorted(
    {
        "AUDI", "BMW", "BYD", "CHERY", "CAOA CHERY", "CHEVROLET", "CITROEN", "FIAT", "FORD", "GWM",
        "HONDA", "HYUNDAI", "JAECOO", "JEEP", "LAND ROVER", "LEAPMOTOR", "MERCEDES-BENZ", "MERCEDES",
        "MINI", "MITSUBISHI", "NISSAN", "PEUGEOT", "PORSCHE", "RAM", "RENAULT", "TOYOTA", "VOLKSWAGEN",
        "VOLVO", "OMODA", "TROLLER", "KIA", "JAC", "LEXUS", "SUZUKI", "SUBARU", "JAGUAR", "DODGE",
        "CHRYSLER", "SMART", "FERRARI", "LAMBORGHINI", "MASERATI", "ALFA ROMEO", "GEELY", "ZEEKR",
        "TESLA", "IVECO", "CAOA", "GM", "VW", "RENAULT", "DS", "EFFA", "LIFAN", "MCLAREN",
    },
    key=len,
    reverse=True,
)
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|ref$|origem$|source$)", re.I)


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def strip_accents(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(c for c in value if not unicodedata.combining(c))


def normalize_brand(value: str | None) -> str:
    raw = strip_accents(clean_text(value)).upper()
    raw = BRAND_ALIASES.get(raw, raw)
    return raw


def display_brand(canonical: str) -> str:
    if not canonical:
        return ""
    return BRAND_DISPLAY.get(canonical, canonical.title())


def split_brand_model(title: str) -> tuple[str, str]:
    """Separa a marca do título usando a lista de marcas conhecidas (parser genérico)."""
    title = clean_text(title)
    upper = strip_accents(title).upper()
    for brand in KNOWN_BRANDS:
        if upper == brand:
            return normalize_brand(brand), ""
        if upper.startswith(brand + " "):
            return normalize_brand(brand), title[len(brand):].strip()
    return "", title


def parse_money(value: str | None) -> tuple[float | None, bool]:
    """Retorna (preço, sob_consulta)."""
    text = clean_text(value)
    if not text:
        return None, False
    if "consulta" in text.lower():
        return None, True
    digits = text.replace("R$", "").replace(" ", "")
    if "," in digits:
        digits = digits.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+\.(\d{1,2}|\d{4,})", digits):
        pass  # ponto decimal (ex.: "174990.00000" em JSON-LD); "93.900" segue como milhar
    else:
        digits = digits.replace(".", "")
    try:
        price = float(digits)
    except ValueError:
        return None, False
    return (price if price > 0 else None), False


def parse_km(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    match = KM_RE.search(value) or re.search(r"(\d[\d.]*)", value)
    if not match:
        return None
    try:
        return int(match.group(1).replace(".", ""))
    except ValueError:
        return None


def parse_years(text: str | None, now_year: int | None = None) -> tuple[int | None, int | None]:
    """Retorna (ano_fabricacao, ano_modelo)."""
    text = clean_text(text)
    now_year = now_year or datetime.now().year
    pair = YEAR_PAIR_RE.search(text)
    if pair:
        fab, mod = int(pair.group(1)), int(pair.group(2))
        if 1950 <= fab <= now_year + 2 and 1950 <= mod <= now_year + 2:
            return fab, mod
    single = YEAR_RE.search(text)
    if single:
        year = int(single.group(1))
        if 1950 <= year <= now_year + 2:
            return None, year
    return None, None


def normalize_url(url: str | None, base_url: str = "") -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.startswith(("javascript:", "mailto:", "tel:", "#", "whatsapp:")):
        return None
    absolute = urljoin(base_url, url) if base_url else url
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https"):
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


@dataclass
class RawVehicle:
    """Saída bruta de um parser de site."""

    brand: str = ""
    model: str = ""
    version: str = ""
    year_text: str = ""
    km: int | str | None = None
    price_text: str = ""
    url: str | None = None
    source_id: str | None = None
    title: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class NormalizedVehicle:
    vehicle_key: str
    key_type: str
    brand: str
    brand_display: str
    model: str
    version: str
    year_fabrication: int | None
    year_model: int | None
    km: int | None
    price: float | None
    price_on_request: bool
    price_text: str
    url: str | None
    source_id: str | None
    title: str

    def to_dict(self) -> dict:
        return asdict(self)


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


def build_vehicle_key(source_id: str | None, url: str | None, brand: str, model: str, version: str,
                      year_model: int | None, km: int | None) -> tuple[str, str]:
    if source_id:
        return f"id:{clean_text(str(source_id)).lower()}", "source_id"
    if url:
        return f"url:{_hash(url)}", "url"
    parts = "|".join([brand, strip_accents(model).upper(), strip_accents(version).upper(), str(year_model or ""), str(km or "")])
    return f"attr:{_hash(parts)}", "attributes"


def normalize_vehicle(raw: RawVehicle, base_url: str = "") -> NormalizedVehicle | None:
    brand = normalize_brand(raw.brand)
    model = clean_text(raw.model).upper()
    version = clean_text(raw.version).upper()
    if not brand and not model:
        return None
    fab, mod = parse_years(raw.year_text)
    price, on_request = parse_money(raw.price_text)
    km = parse_km(raw.km)
    url = normalize_url(raw.url, base_url)
    source_id = clean_text(str(raw.source_id)) if raw.source_id else None
    key, key_type = build_vehicle_key(source_id, url, brand, model, version, mod, km)
    return NormalizedVehicle(
        vehicle_key=key,
        key_type=key_type,
        brand=brand,
        brand_display=display_brand(brand),
        model=model,
        version=version,
        year_fabrication=fab,
        year_model=mod,
        km=km,
        price=price,
        price_on_request=on_request,
        price_text=clean_text(raw.price_text),
        url=url,
        source_id=source_id,
        title=clean_text(raw.title) or clean_text(f"{brand} {model} {version}"),
    )


def normalize_and_dedupe(raws: list[RawVehicle], base_url: str = "") -> tuple[list[NormalizedVehicle], int, int]:
    """Retorna (veículos únicos, duplicados descartados, inválidos descartados)."""
    seen: dict[str, NormalizedVehicle] = {}
    duplicates = 0
    invalid = 0
    for raw in raws:
        vehicle = normalize_vehicle(raw, base_url)
        if vehicle is None:
            invalid += 1
            continue
        if vehicle.vehicle_key in seen:
            duplicates += 1
            continue
        seen[vehicle.vehicle_key] = vehicle
    return list(seen.values()), duplicates, invalid
