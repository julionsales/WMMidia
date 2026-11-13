"""Parser da Azul Premium (plataforma AutoCerto).

Estrutura verificada em 30/10/2026 em https://azulpremium.com.br/Veiculos:
- cards `div.result-item`;
- título `h4.result-item-title-new` = "MARCA <b>MODELO</b>";
- versão em `h4.result-item-sub-title`;
- ano "2021/2022" e "62.000 km" no corpo; preço em `.price`;
- link `/Veiculo/<slug>/<ID>/detalhes` (ID numérico = identificador do anúncio);
- total anunciado em "102 veículos encontrados".

Layout mais novo da mesma plataforma (Gilcar, verificado em 12/11/2026): marca em
`.vehicle-brand-name` e modelo em `.vehicle-brand-model`, sem `h4.result-item-title-new`.

Correção em relação ao script original: a marca vem da estrutura do card, e não de
uma lista fixa (o original descartava, por exemplo, OMODA e TROLLER).
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from app.services.inventory.normalize import KM_RE, PRICE_RE, YEAR_PAIR_RE, RawVehicle, clean_text
from app.services.inventory.parsers.base import COUNT_RE, ParseResult, soup_of, text_of

ID_RE = re.compile(r"/Veiculo/[^/]+/(\d+)", re.I)


def parse_azul_html(html: str, base_url: str) -> ParseResult:
    soup = soup_of(html)
    result = ParseResult(final_url=base_url)
    count = COUNT_RE.search(soup.get_text(" "))
    if count:
        result.declared_total = int(count.group(1))

    for card in soup.select("div.result-item"):
        brand_node = card.select_one(".vehicle-brand-name")
        model_node = card.select_one(".vehicle-brand-model")
        if brand_node is not None and model_node is not None:
            # Layout mais novo da AutoCerto (ex.: Gilcar): marca e modelo em campos próprios.
            brand, model = text_of(brand_node), text_of(model_node)
            full_title = clean_text(f"{brand} {model}")
        else:
            title_node = card.select_one(".result-item-title-new") or card.find(["h3", "h4"])
            if title_node is None:
                continue
            model = text_of(title_node.find("b"))
            full_title = text_of(title_node)
            brand = clean_text(full_title[: len(full_title) - len(model)]) if model and full_title.endswith(model) else ""
            if not brand:
                brand, _, model = full_title.partition(" ")
        version = text_of(card.select_one(".result-item-sub-title"))
        body = text_of(card)
        price_node = card.select_one(".price")
        price_match = PRICE_RE.search(text_of(price_node) or body)
        year_match = YEAR_PAIR_RE.search(body)
        km_match = KM_RE.search(body)
        link = None
        source_id = None
        for anchor in card.find_all("a", href=True):
            match = ID_RE.search(anchor["href"])
            if match:
                link, source_id = urljoin(base_url, anchor["href"]), match.group(1)
                break
        result.vehicles.append(
            RawVehicle(
                brand=brand,
                model=model,
                version=version,
                year_text=year_match.group(0) if year_match else body,
                km=km_match.group(0) if km_match else None,
                price_text=price_match.group(0) if price_match else "",
                url=link,
                source_id=source_id,
                title=full_title,
            )
        )
    result.pages_fetched = 1
    return result


class AzulParser:
    key = "azul"
    label = "Azul Premium (AutoCerto)"
    requires_browser = False

    def collect(self, url, fetchers, options) -> ParseResult:
        resp = fetchers.http.get(url)
        result = parse_azul_html(resp.text, resp.url)
        result.final_url = resp.url
        return result
