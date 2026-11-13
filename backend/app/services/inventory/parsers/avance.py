"""Parser da Avance Premium (WordPress + listagem via admin-ajax).

Verificado em 30/10/2026: a página /estoque/ não traz veículos no HTML; o script da
página chama `POST /wp-admin/admin-ajax.php` com `action=filtrar_estoque&pagina=N`,
que devolve `<div class="estoque-data" data-total-filtrado="22">` + `<ul>` com
`li.loopcarros` (6 por página). Cada card tem `p.titmarca`, `a.titulocarro` (modelo),
`p.titversao` ("2026 - VERSÃO"), quilometragem, `.wrappreco` e `data-veiculo-id`.

O script original usava Playwright + heurística genérica e gravava o card inteiro no
campo modelo. Aqui o mesmo endpoint usado pelo navegador é lido diretamente; se ele
deixar de responder, é possível trocar o parser da empresa para "playwright".
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from app.services.inventory.normalize import KM_RE, PRICE_RE, RawVehicle
from app.services.inventory.parsers.base import ParseResult, soup_of, text_of

VERSION_RE = re.compile(r"^\s*((?:19|20)\d{2}(?:\s*/\s*(?:19|20)\d{2})?)\s*-\s*(.*)$")


def parse_avance_fragment(html: str, base_url: str) -> ParseResult:
    soup = soup_of(html)
    result = ParseResult(final_url=base_url)
    data = soup.select_one(".estoque-data[data-total-filtrado]")
    if data is not None:
        try:
            result.declared_total = int(data["data-total-filtrado"])
        except (TypeError, ValueError):
            pass
    for card in soup.select("li.loopcarros"):
        link = card.select_one("a.titulocarro") or card.select_one("a.fotodestaque")
        model = text_of(card.select_one("a.titulocarro"))
        version_text = text_of(card.select_one("p.titversao"))
        year, version = "", version_text
        match = VERSION_RE.match(version_text)
        if match:
            year, version = match.group(1), match.group(2)
        km_node = card.select_one(".wrapkm") or card
        price_node = card.select_one(".wrappreco")
        price_text = text_of(price_node)
        price_match = PRICE_RE.search(price_text)
        if not price_match and price_text:
            price_match = re.search(r"\d[\d.]*,?\d*", price_text)
        id_node = card.select_one("[data-veiculo-id]")
        km_match = KM_RE.search(text_of(km_node))
        result.vehicles.append(
            RawVehicle(
                brand=text_of(card.select_one("p.titmarca")),
                model=model,
                version=version,
                year_text=year,
                km=km_match.group(0) if km_match else None,
                price_text=price_match.group(0) if price_match else price_text,
                url=link.get("href") if link else None,
                source_id=id_node.get("data-veiculo-id") if id_node else None,
                title=f"{text_of(card.select_one('p.titmarca'))} {model} {version_text}",
            )
        )
    result.pages_fetched = 1
    return result


def ajax_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/wp-admin/admin-ajax.php", "", ""))


class AvanceParser:
    key = "avance"
    label = "Avance Premium (WordPress/admin-ajax)"
    requires_browser = False

    def collect(self, url, fetchers, options) -> ParseResult:
        max_pages = int(options.get("max_pages", 30))
        endpoint = ajax_url(url)
        merged = ParseResult(final_url=url)
        merged.pages_fetched = 0
        page = 1
        while True:
            if page > max_pages:
                merged.reached_end = False
                merged.warnings.append(f"Limite de {max_pages} páginas atingido")
                break
            resp = fetchers.http.post(endpoint, data={"action": "filtrar_estoque", "pagina": str(page)},
                                      headers={"X-Requested-With": "XMLHttpRequest", "Referer": url})
            part = parse_avance_fragment(resp.text, url)
            merged.pages_fetched += 1
            if part.declared_total is not None:
                merged.declared_total = part.declared_total
            if not part.vehicles:
                break
            merged.vehicles.extend(part.vehicles)
            if merged.declared_total is not None and len(merged.vehicles) >= merged.declared_total:
                break
            page += 1
        return merged
