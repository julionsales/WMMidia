"""Parser genérico (heurístico), herdado do `automation.py` original.

Usado para sites sem parser dedicado ("generic" = HTML estático, "playwright" = página
renderizada). Procura blocos com marca conhecida + preço + ano/km. Por ser heurístico,
não conhece o total anunciado; a coleta só é considerada completa pelas regras de
segurança de app.services.inventory.service (proporção mínima vs. última coleta).
"""

from __future__ import annotations

import json

from app.services.inventory.normalize import (
    KM_RE,
    PRICE_RE,
    YEAR_PAIR_RE,
    YEAR_RE,
    RawVehicle,
    clean_text,
    split_brand_model,
)
from app.services.inventory.parsers.base import COUNT_RE, ParseResult, soup_of, text_of

DETAIL_WORDS = ("ver mais", "mais detalhes", "detalhes", "ver oferta", "saiba mais")


def _jsonld_cars(soup) -> list[RawVehicle]:
    found: list[RawVehicle] = []

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            kind = node.get("@type")
            if kind in ("Car", "Vehicle", "Product") and node.get("brand"):
                brand = node["brand"].get("name") if isinstance(node["brand"], dict) else node["brand"]
                offers = node.get("offers") or {}
                price = offers.get("price") if isinstance(offers, dict) else None
                km = (node.get("mileageFromOdometer") or {}).get("value") if isinstance(node.get("mileageFromOdometer"), dict) else None
                found.append(RawVehicle(
                    brand=str(brand or ""), model=str(node.get("model") or ""), version=str(node.get("name") or ""),
                    year_text=str(node.get("vehicleModelDate") or node.get("productionDate") or ""),
                    km=int(float(km)) if km else None, price_text=f"R$ {price}" if price else "",
                    url=node.get("url"), title=str(node.get("name") or ""),
                ))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(script.string or ""))
        except (ValueError, TypeError):
            continue
    return found


def _extract_link(container, base_url: str) -> str | None:
    anchors = container.find_all("a", href=True)
    for anchor in anchors:
        if any(w in text_of(anchor).lower() for w in DETAIL_WORDS):
            return anchor["href"]
    for anchor in anchors:
        href = anchor["href"]
        if href and href not in ("#", "/") and not href.startswith(("javascript", "tel:", "mailto:", "https://wa.me", "whatsapp")):
            return href
    return None


def parse_generic_html(html: str, base_url: str) -> ParseResult:
    soup = soup_of(html)
    result = ParseResult(final_url=base_url, pages_fetched=1)
    count = COUNT_RE.search(soup.get_text(" "))
    if count:
        result.declared_total = int(count.group(1))

    jsonld = _jsonld_cars(soup)
    if jsonld:
        result.vehicles = jsonld
        result.warnings.append("Dados extraídos de JSON-LD (schema.org)")
        return result

    seen_containers = set()
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "a"]):
        title = text_of(heading)
        if len(title) > 120:
            continue
        brand, model = split_brand_model(title)
        if not (brand and model):
            continue
        container = heading
        for _ in range(8):
            container = container.parent
            if container is None:
                break
            text = text_of(container)
            if len(text) > 1500:
                container = None
                break
            if PRICE_RE.search(text) and (YEAR_RE.search(text) or KM_RE.search(text)):
                break
        if container is None or id(container) in seen_containers:
            continue
        text = text_of(container)
        if not PRICE_RE.search(text):
            continue
        seen_containers.add(id(container))
        model_words = model.split()
        result.vehicles.append(RawVehicle(
            brand=brand,
            model=model_words[0] if model_words else model,
            version=" ".join(model_words[1:]),
            year_text=(YEAR_PAIR_RE.search(text) or YEAR_RE.search(text)).group(0) if YEAR_RE.search(text) else "",
            km=KM_RE.search(text).group(0) if KM_RE.search(text) else None,
            price_text=PRICE_RE.search(text).group(0),
            url=_extract_link(container, base_url),
            title=clean_text(title),
        ))
    return result


class GenericParser:
    key = "generic"
    label = "Genérico (HTML estático, heurístico)"
    requires_browser = False

    def collect(self, url, fetchers, options) -> ParseResult:
        resp = fetchers.http.get(url)
        result = parse_generic_html(resp.text, resp.url)
        result.final_url = resp.url
        return result


class PlaywrightParser:
    key = "playwright"
    label = "Genérico com navegador (páginas com JavaScript)"
    requires_browser = True

    def collect(self, url, fetchers, options) -> ParseResult:
        if fetchers.browser is None:
            raise RuntimeError("Navegador (Playwright) desabilitado neste ambiente")
        resp = fetchers.browser.render(url, load_more=bool(options.get("load_more")))
        result = parse_generic_html(resp.text, resp.url)
        result.final_url = resp.url
        return result
