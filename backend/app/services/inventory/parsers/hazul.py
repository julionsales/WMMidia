"""Parser do Grupo Hazul (plataforma DealerSpace).

Estrutura verificada em 30/10/2026:
- cards `.c-stock-card` com id `vehicle-stock-seminovos-vehicle-id-<ID>`;
- marca `.c-stock-card__brand` (ex.: "CITROËN"), título `.c-stock-card__title`,
  `.c-stock-card__km`, `.c-stock-card__year`, `.c-stock-card__price`;
- link `a.c-stock-card__body-vdp-link`;
- total em "Localizados N resultados"; paginação em `.stock-pagination a`.

Correções em relação ao original: o original não reconhecia "CITROËN" (com trema),
gravava o texto inteiro do card no campo modelo e não capturava o link.
O título é "MODELO VERSÃO". O modelo vem do JSON-LD da página (`itemOffered.model`)
quando o título coincide; sem JSON-LD, a primeira palavra vira o modelo (heurística).
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from app.services.inventory.normalize import KM_RE, PRICE_RE, YEAR_PAIR_RE, YEAR_RE, RawVehicle, clean_text
from app.services.inventory.parsers.base import ParseResult, soup_of, text_of

TOTAL_RE = re.compile(r"Localizad[oa]s\s+(\d{1,6})\s+resultados?", re.I)
CARD_ID_RE = re.compile(r"vehicle-id-(\d+)")


def jsonld_models(soup) -> dict[str, str]:
    """Mapa título -> modelo extraído do JSON-LD (schema.org Car)."""
    models: dict[str, str] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        offers = data.get("offers", []) if isinstance(data, dict) else []
        for offer in offers if isinstance(offers, list) else []:
            item = offer.get("itemOffered") or {}
            name, model = clean_text(item.get("name")), clean_text(item.get("model"))
            if name and model:
                models[name.upper()] = model
    return models


def split_model_version(title: str, known: dict[str, str]) -> tuple[str, str]:
    model = known.get(title.upper())
    if model and title.upper().startswith(model.upper()):
        return title[: len(model)], title[len(model):].strip()
    model, _, version = title.partition(" ")
    return model, version


def parse_hazul_html(html: str, base_url: str) -> tuple[ParseResult, list[str]]:
    soup = soup_of(html)
    result = ParseResult(final_url=base_url)
    total = TOTAL_RE.search(soup.get_text(" "))
    if total:
        result.declared_total = int(total.group(1))
    known_models = jsonld_models(soup)

    for card in soup.select(".c-stock-card"):
        title = text_of(card.select_one(".c-stock-card__title"))
        if not title:
            continue
        model, version = split_model_version(title, known_models)
        body = text_of(card)
        year_text = text_of(card.select_one(".c-stock-card__year")) or body
        km_text = text_of(card.select_one(".c-stock-card__km"))
        price_text = text_of(card.select_one(".c-stock-card__price"))
        link_node = card.select_one("a.c-stock-card__body-vdp-link") or card.select_one("a[href*='/estoque/']")
        id_match = CARD_ID_RE.search(card.get("id", ""))
        price_match = PRICE_RE.search(price_text or body)
        year_match = YEAR_PAIR_RE.search(year_text) or YEAR_RE.search(year_text)
        km_match = KM_RE.search(km_text or body)
        result.vehicles.append(
            RawVehicle(
                brand=text_of(card.select_one(".c-stock-card__brand")),
                model=model,
                version=version,
                year_text=year_match.group(0) if year_match else "",
                km=km_match.group(0) if km_match else None,
                price_text=price_match.group(0) if price_match else "",
                url=urljoin(base_url, link_node["href"]) if link_node and link_node.get("href") else None,
                source_id=id_match.group(1) if id_match else None,
                title=title,
            )
        )
    next_pages = []
    for anchor in soup.select(".stock-pagination a[href]"):
        href = anchor["href"]
        if href and not href.startswith(("#", "javascript")):
            next_pages.append(urljoin(base_url, href))
    result.pages_fetched = 1
    return result, next_pages


class HazulParser:
    key = "hazul"
    label = "Grupo Hazul (DealerSpace)"
    requires_browser = False

    def collect(self, url, fetchers, options) -> ParseResult:
        max_pages = int(options.get("max_pages", 30))
        resp = fetchers.http.get(url)
        merged, pending = parse_hazul_html(resp.text, resp.url)
        merged.final_url = resp.url
        visited = {resp.url, url}
        while pending:
            page_url = pending.pop(0)
            if page_url in visited:
                continue
            if merged.pages_fetched >= max_pages:
                merged.reached_end = False
                merged.warnings.append(f"Limite de {max_pages} páginas atingido")
                break
            visited.add(page_url)
            try:
                page = fetchers.http.get(page_url)
            except Exception as exc:  # noqa: BLE001 - registrado como página com falha
                merged.pages_failed += 1
                merged.warnings.append(f"Falha ao ler página adicional: {type(exc).__name__}")
                continue
            part, more = parse_hazul_html(page.text, page.url)
            merged.vehicles.extend(part.vehicles)
            merged.pages_fetched += 1
            pending.extend(u for u in more if u not in visited)
        return merged
