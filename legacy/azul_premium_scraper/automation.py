"""
Automation - Scraper multiempresa de estoque e gerador de briefing.

Uso:
    python automation.py
    python automation.py --config config.json
    python automation.py --out output
    python automation.py --debug

O config.json esperado:

{
  "output_dir": "output",
  "empresas": [
    {
      "nome": "Azul Premium",
      "url": "https://azulpremium.com.br/Veiculos",
      "parser": "azul",
      "min_model_stock": 4
    },
    {
      "nome": "Grupo Hazul",
      "url": "https://www.grupohazul.com.br/divem-citroen-seminovos/estoque/seminovos",
      "parser": "hazul",
      "min_model_stock": 3
    },
    {
      "nome": "Avance Premium",
      "url": "https://avancepremium.com.br/estoque/",
      "parser": "playwright",
      "load_more": true,
      "min_model_stock": 3
    }
  ]
}

Parsers:
    azul       -> estrutura da Azul Premium
    hazul      -> estrutura do Grupo Hazul
    playwright -> abre o site em navegador Chromium
    requests   -> HTML estático
    auto       -> escolhe parser conhecido pelo domínio
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

DEFAULT_URL = "https://azulpremium.com.br/Veiculos"
DEFAULT_OUTPUT = "output"

BRANDS = [
    "AUDI", "BMW", "BYD", "CHERY", "CAOA CHERY", "CHEVROLET", "CITROEN",
    "FIAT", "FORD", "GWM", "HONDA", "HYUNDAI", "JAECOO", "JEEP",
    "LAND ROVER", "LEAPMOTOR", "MERCEDES-BENZ", "MERCEDES", "MINI",
    "MITSUBISHI", "NISSAN", "PEUGEOT", "PORSCHE", "RAM", "RENAULT",
    "TOYOTA", "VOLKSWAGEN", "VOLVO"
]

PRICE_RE = re.compile(r"R\$\s*(?:[\d.]+(?:,\d{2})?|Sob Consulta)", re.I)
YEAR_RE = re.compile(r"\b(20\d{2}/20\d{2}|20\d{2})\b")
KM_RE = re.compile(r"\b([\d.]+)\s*(?:km|KM)\b")
COUNT_RE = re.compile(r"(\d+)\s+ve[ií]culos\s+encontrados", re.I)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def safe_folder_name(name: str) -> str:
    value = unicodedata.normalize("NFKD", name)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or "empresa"


def parse_money(value: str) -> float | None:
    if not value:
        return None

    if "consulta" in value.lower():
        return None

    value = (
        value.replace("R$", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        return float(value)
    except ValueError:
        return None


def normalize_url(url: str) -> str:
    return url.rstrip("/") + "/"


def fetch_html(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    logging.info("Acessando %s", url)

    response = requests.get(
        url,
        headers=headers,
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()

    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def split_brand_model(title: str) -> tuple[str, str]:
    title = clean_text(title)
    upper = title.upper()

    for brand in sorted(BRANDS, key=len, reverse=True):
        if upper == brand:
            return brand, ""

        if upper.startswith(brand + " "):
            return brand, title[len(brand):].strip()

    return "", title


def is_brand_model_heading(text: str) -> bool:
    brand, model = split_brand_model(text)
    return bool(brand and model)


def extract_basic_vehicle(text: str, base_url: str = "") -> dict:
    text = clean_text(text)

    price_match = PRICE_RE.search(text)
    year_match = YEAR_RE.search(text)
    km_match = KM_RE.search(text)

    price_raw = price_match.group(0) if price_match else ""
    year = year_match.group(1) if year_match else ""
    km_raw = km_match.group(1) if km_match else ""

    return {
        "ano": year,
        "km": int(km_raw.replace(".", "")) if km_raw else None,
        "preco": parse_money(price_raw),
        "preco_texto": price_raw,
    }


def nearest_vehicle_container(heading):
    current = heading

    for _ in range(10):
        current = current.parent

        if current is None:
            break

        text = clean_text(current.get_text(" ", strip=True))

        has_price = bool(PRICE_RE.search(text))
        has_details = (
            "ver mais" in text.lower()
            or "mais detalhes" in text.lower()
            or "detalhes do veículo" in text.lower()
        )

        if has_price and has_details:
            return current

    return heading.parent


def extract_link(container, base_url: str) -> str:
    for anchor in container.find_all("a", href=True):
        href = anchor.get("href", "")
        text = clean_text(anchor.get_text(" ", strip=True)).lower()

        if (
            "ver mais" in text
            or "mais detalhes" in text
            or "detalhes" in text
        ):
            return urljoin(base_url, href)

    # Fallback: primeiro link que parece apontar para veículo
    for anchor in container.find_all("a", href=True):
        href = anchor.get("href", "")
        if href and href not in ("#", "/"):
            return urljoin(base_url, href)

    return ""


def parse_azul(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen = set()

    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

    for heading in headings:
        title = clean_text(heading.get_text(" ", strip=True))

        if not is_brand_model_heading(title):
            continue

        brand, model = split_brand_model(title)
        container = nearest_vehicle_container(heading)
        text = clean_text(container.get_text(" ", strip=True))

        price_match = PRICE_RE.search(text)
        year_match = YEAR_RE.search(text)
        km_match = KM_RE.search(text)

        if not price_match:
            continue

        price_raw = price_match.group(0)
        version = ""

        headings_inside = container.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6"]
        )

        for i, item in enumerate(headings_inside):
            item_text = clean_text(item.get_text(" ", strip=True))

            if item_text == title and i + 1 < len(headings_inside):
                candidate = clean_text(
                    headings_inside[i + 1].get_text(" ", strip=True)
                )

                if candidate and not is_brand_model_heading(candidate):
                    version = candidate

                break

        link = extract_link(container, base_url)

        key = (
            brand,
            model,
            version,
            year_match.group(1) if year_match else "",
            km_match.group(1) if km_match else "",
            price_raw,
            link,
        )

        if key in seen:
            continue

        seen.add(key)

        records.append(
            {
                "marca": brand.title() if brand != "GWM" else "GWM",
                "modelo": model,
                "versao": version,
                "ano": year_match.group(1) if year_match else "",
                "km": (
                    int(km_match.group(1).replace(".", ""))
                    if km_match
                    else None
                ),
                "preco": parse_money(price_raw),
                "preco_texto": price_raw,
                "link": link,
            }
        )

    return records


def parse_hazul(html: str, base_url: str) -> list[dict]:
    """
    Parser mais permissivo para páginas do Grupo Hazul.

    Como a estrutura pode variar entre lojas/modelos, procura blocos de texto
    contendo preço + KM + ano e tenta identificar marca/modelo nos headings.
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen = set()

    candidates = soup.find_all(
        ["article", "div", "li", "section"]
    )

    for container in candidates:
        text = clean_text(container.get_text(" ", strip=True))

        if len(text) < 30:
            continue

        price_match = PRICE_RE.search(text)
        km_match = KM_RE.search(text)
        year_match = YEAR_RE.search(text)

        if not (price_match and (km_match or year_match)):
            continue

        # Evita pegar um ancestral gigante contendo dezenas de carros.
        if len(text) > 1800:
            continue

        headings = container.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6"]
        )

        title = ""
        brand = ""
        model = ""

        for heading in headings:
            candidate = clean_text(heading.get_text(" ", strip=True))
            b, m = split_brand_model(candidate)

            if b and m:
                title = candidate
                brand = b
                model = m
                break

        if not brand:
            # Procura qualquer linha que comece com marca conhecida.
            for line in text.split("  "):
                b, m = split_brand_model(clean_text(line))
                if b and m:
                    title = line
                    brand = b
                    model = m
                    break

        if not brand:
            continue

        price_raw = price_match.group(0)
        link = extract_link(container, base_url)

        key = (
            brand,
            model,
            year_match.group(1) if year_match else "",
            km_match.group(1) if km_match else "",
            price_raw,
            link,
        )

        if key in seen:
            continue

        seen.add(key)

        records.append(
            {
                "marca": brand.title() if brand != "GWM" else "GWM",
                "modelo": model,
                "versao": "",
                "ano": year_match.group(1) if year_match else "",
                "km": (
                    int(km_match.group(1).replace(".", ""))
                    if km_match
                    else None
                ),
                "preco": parse_money(price_raw),
                "preco_texto": price_raw,
                "link": link,
            }
        )

    return records


def playwright_html(
    url: str,
    output_dir: Path,
    load_more: bool = False,
    timeout_ms: int = 45000,
) -> tuple[str, str]:
    """
    Abre a página com Chromium e retorna HTML + URL final.

    Se nada for encontrado, salva:
        debug_page.html
        debug_screenshot.png

    Isso ajuda a diferenciar parser incorreto de bloqueio/anti-bot.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright não está instalado. Execute: "
            "pip install -r requirements.txt && playwright install chromium"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            locale="pt-BR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36"
            ),
        )

        page = context.new_page()

        logging.info("Playwright abrindo %s", url)

        try:
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )

            logging.info(
                "Playwright status=%s final_url=%s",
                response.status if response else "sem response",
                page.url,
            )

            page.wait_for_timeout(4000)

            if load_more:
                for _ in range(15):
                    buttons = page.get_by_text(
                        re.compile(
                            r"carregar\s+mais|mostrar\s+mais|ver\s+mais",
                            re.I,
                        )
                    )

                    if buttons.count() == 0:
                        break

                    clicked = False

                    for i in range(buttons.count()):
                        try:
                            button = buttons.nth(i)

                            if button.is_visible():
                                button.click(timeout=2500)
                                page.wait_for_timeout(1500)
                                clicked = True
                                break
                        except Exception:
                            continue

                    if not clicked:
                        break

            page.wait_for_timeout(1500)

            html = page.content()

            # Salva diagnóstico sempre que solicitado pelo caller através
            # do arquivo temporário; o caller decide se precisa mantê-lo.
            return html, page.url

        finally:
            browser.close()


def parse_with_playwright(
    url: str,
    output_dir: Path,
    load_more: bool = False,
) -> list[dict]:
    html, final_url = playwright_html(
        url=url,
        output_dir=output_dir,
        load_more=load_more,
    )

    records = parse_azul(html, final_url)

    if not records:
        records = parse_hazul(html, final_url)

    if not records:
        # Diagnóstico da resposta real recebida.
        (output_dir / "debug_page.html").write_text(
            html,
            encoding="utf-8",
            errors="ignore",
        )

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    locale="pt-BR",
                )
                page = context.new_page()

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=45000,
                )
                page.wait_for_timeout(4000)

                if load_more:
                    for _ in range(10):
                        buttons = page.get_by_text(
                            re.compile(
                                r"carregar\s+mais|mostrar\s+mais|ver\s+mais",
                                re.I,
                            )
                        )

                        if buttons.count() == 0:
                            break

                        clicked = False

                        for i in range(buttons.count()):
                            try:
                                button = buttons.nth(i)

                                if button.is_visible():
                                    button.click(timeout=2000)
                                    page.wait_for_timeout(1000)
                                    clicked = True
                                    break
                            except Exception:
                                continue

                        if not clicked:
                            break

                page.screenshot(
                    path=str(output_dir / "debug_screenshot.png"),
                    full_page=True,
                )

                browser.close()

        except Exception as exc:
            logging.warning(
                "Não foi possível gerar screenshot de diagnóstico: %s",
                exc,
            )

        logging.warning(
            "Playwright não encontrou veículos. "
            "HTML e screenshot de diagnóstico foram salvos em %s",
            output_dir,
        )

    return records


def choose_parser(company: dict) -> str:
    parser = company.get("parser", "auto").lower()

    if parser != "auto":
        return parser

    hostname = urlparse(company["url"]).netloc.lower()

    if "azulpremium" in hostname:
        return "azul"

    if "grupohazul" in hostname:
        return "hazul"

    if "avancepremium" in hostname:
        return "playwright"

    return "requests"


def parse_company(
    company: dict,
    output_dir: Path,
) -> list[dict]:
    url = company["url"]
    parser = choose_parser(company)

    logging.info(
        "Empresa=%s | parser=%s | url=%s",
        company["nome"],
        parser,
        url,
    )

    if parser == "playwright":
        return parse_with_playwright(
            url=url,
            output_dir=output_dir,
            load_more=bool(company.get("load_more", False)),
        )

    html = fetch_html(url)

    if parser == "azul":
        return parse_azul(html, url)

    if parser == "hazul":
        return parse_hazul(html, url)

    if parser == "requests":
        # Tenta os parsers conhecidos antes do fallback.
        records = parse_azul(html, url)

        if not records:
            records = parse_hazul(html, url)

        return records

    raise ValueError(
        f"Parser desconhecido: {parser}. "
        "Use azul, hazul, playwright, requests ou auto."
    )


def build_dataframe(records: list[dict]) -> pd.DataFrame:
    if not records:
        raise RuntimeError(
            "Nenhum veículo foi extraído. "
            "O layout pode ter mudado, os dados podem ser carregados "
            "por JavaScript ou o site pode ter retornado uma página diferente."
        )

    df = pd.DataFrame(records)

    expected = [
        "marca",
        "modelo",
        "versao",
        "ano",
        "km",
        "preco",
        "preco_texto",
        "link",
    ]

    for column in expected:
        if column not in df.columns:
            df[column] = ""

    df = df[expected]

    df = df.drop_duplicates(
        subset=[
            "marca",
            "modelo",
            "versao",
            "ano",
            "km",
            "preco",
            "link",
        ]
    ).reset_index(drop=True)

    df.insert(0, "id", range(1, len(df) + 1))

    return df


def ranking_modelos(df: pd.DataFrame) -> pd.DataFrame:
    result = (
        df.groupby(["marca", "modelo"], as_index=False)
        .agg(
            estoque=("id", "count"),
            preco_min=("preco", "min"),
            preco_max=("preco", "max"),
            km_medio=("km", "mean"),
        )
        .sort_values(
            ["estoque", "marca", "modelo"],
            ascending=[False, True, True],
        )
    )

    return result


def ranking_marcas(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("marca", as_index=False)
        .agg(
            estoque=("id", "count"),
            preco_min=("preco", "min"),
            preco_max=("preco", "max"),
        )
        .sort_values(
            ["estoque", "marca"],
            ascending=[False, True],
        )
    )


def classify_content(
    models: pd.DataFrame,
    min_model_stock: int,
) -> pd.DataFrame:
    result = models.copy()

    def category(row):
        stock = int(row["estoque"])
        price_min = row["preco_min"]

        if stock >= min_model_stock:
            return "Giro de estoque"

        if pd.notna(price_min) and float(price_min) >= 400000:
            return "Hero car / Premium"

        if pd.notna(price_min) and float(price_min) <= 180000:
            return "Custo-benefício"

        return "Oportunidade"

    result["categoria_conteudo"] = result.apply(
        category,
        axis=1,
    )

    return result


def format_brl(value) -> str:
    if pd.isna(value) or value is None:
        return "Sob consulta"

    return (
        f"R$ {float(value):,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def make_briefing_docx(
    company_name: str,
    df: pd.DataFrame,
    brands: pd.DataFrame,
    classified: pd.DataFrame,
    output_path: Path,
    source_url: str,
):
    doc = Document()

    styles = doc.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"].font.size = Pt(10)

    title = doc.add_heading(
        f"{company_name.upper()} — BRIEFING AUTOMÁTICO DE CRIATIVOS",
        0,
    )
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.add_run("Data da coleta: ").bold = True
    p.add_run(datetime.now().strftime("%d/%m/%Y %H:%M"))
    p.add_run("\nFonte: ").bold = True
    p.add_run(source_url)
    p.add_run("\nVeículos extraídos: ").bold = True
    p.add_run(str(len(df)))

    doc.add_heading("1. Estoque por marca", level=1)

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"

    table.rows[0].cells[0].text = "Marca"
    table.rows[0].cells[1].text = "Qtd."

    for _, row in brands.head(20).iterrows():
        cells = table.add_row().cells
        cells[0].text = str(row["marca"])
        cells[1].text = str(int(row["estoque"]))

    doc.add_heading("2. Modelos prioritários", level=1)

    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"

    headers = [
        "Marca",
        "Modelo",
        "Estoque",
        "Faixa de preço",
        "Categoria",
    ]

    for i, header in enumerate(headers):
        table.rows[0].cells[i].text = header

    for _, row in classified.head(30).iterrows():
        cells = table.add_row().cells

        cells[0].text = str(row["marca"])
        cells[1].text = str(row["modelo"])
        cells[2].text = str(int(row["estoque"]))

        cells[3].text = (
            f"{format_brl(row['preco_min'])} — "
            f"{format_brl(row['preco_max'])}"
        )

        cells[4].text = str(row["categoria_conteudo"])

    doc.add_heading("3. Pilares sugeridos", level=1)

    for item in [
        "Giro de estoque: modelos com maior quantidade de unidades.",
        "Hero cars / Premium: veículos de alto valor e forte apelo visual.",
        "Custo-benefício: veículos com preço inicial mais acessível.",
        "Oportunidades: modelos com estoque menor ou características específicas.",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("4. Dados disponíveis", level=1)

    for item in [
        "Marca",
        "Modelo",
        "Versão",
        "Ano/modelo",
        "Quilometragem",
        "Preço",
        "Link do veículo",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("5. Observação", level=1)

    doc.add_paragraph(
        "Os dados representam uma fotografia do estoque no momento da coleta. "
        "Preço, quilometragem e disponibilidade podem mudar. "
        "Conferir o veículo no site antes da publicação de qualquer peça."
    )

    doc.save(output_path)


def export_files(
    company_name: str,
    df: pd.DataFrame,
    brands: pd.DataFrame,
    classified: pd.DataFrame,
    output_dir: Path,
    source_url: str,
    parser: str,
):
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    df.to_csv(
        output_dir / "estoque_veiculos.csv",
        index=False,
        encoding="utf-8-sig",
    )

    brands.to_csv(
        output_dir / "ranking_marcas.csv",
        index=False,
        encoding="utf-8-sig",
    )

    classified.to_csv(
        output_dir / "ranking_modelos.csv",
        index=False,
        encoding="utf-8-sig",
    )

    payload = {
        "empresa": company_name,
        "coleta_em": datetime.now().isoformat(timespec="seconds"),
        "fonte": source_url,
        "parser": parser,
        "total_veiculos": int(len(df)),
        "veiculos": df.to_dict(orient="records"),
    }

    with open(
        output_dir / "estoque.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    excel_path = output_dir / "estoque.xlsx"

    with pd.ExcelWriter(
        excel_path,
        engine="openpyxl",
    ) as writer:
        df.to_excel(
            writer,
            sheet_name="Estoque",
            index=False,
        )

        brands.to_excel(
            writer,
            sheet_name="Ranking Marcas",
            index=False,
        )

        classified.to_excel(
            writer,
            sheet_name="Ranking Modelos",
            index=False,
        )

    docx_path = output_dir / "briefing_criativos.docx"

    make_briefing_docx(
        company_name=company_name,
        df=df,
        brands=brands,
        classified=classified,
        output_path=docx_path,
        source_url=source_url,
    )

    metadata = {
        "empresa": company_name,
        "arquivo_gerado_em": timestamp,
        "total_extraido": int(len(df)),
        "parser": parser,
        "arquivos": [
            "estoque_veiculos.csv",
            "ranking_marcas.csv",
            "ranking_modelos.csv",
            "estoque.json",
            "estoque.xlsx",
            "briefing_criativos.docx",
        ],
    }

    with open(
        output_dir / "coleta_info.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=2,
        )


def save_error(
    company_name: str,
    company_output: Path,
    message: str,
):
    company_output.mkdir(parents=True, exist_ok=True)

    payload = {
        "empresa": company_name,
        "erro": message,
        "registrado_em": datetime.now().isoformat(timespec="seconds"),
    }

    with open(
        company_output / "erro.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Configuração não encontrada: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    # Compatibilidade com configuração antiga de empresa única.
    if "empresas" not in config:
        config = {
            "output_dir": config.get(
                "output_dir",
                DEFAULT_OUTPUT,
            ),
            "empresas": [
                {
                    "nome": "Azul Premium",
                    "url": config.get(
                        "url",
                        DEFAULT_URL,
                    ),
                    "parser": config.get(
                        "parser",
                        "auto",
                    ),
                    "min_model_stock": config.get(
                        "min_model_stock",
                        4,
                    ),
                }
            ],
        }

    return config


def process_company(
    company: dict,
    root_output: Path,
    debug: bool = False,
):
    name = company["nome"]
    url = company["url"]

    company_output = (
        root_output / safe_folder_name(name)
    )

    parser = choose_parser(company)

    print(f"\n{'=' * 70}")
    print(f"EMPRESA: {name}")
    print(f"PARSER : {parser}")
    print(f"URL    : {url}")
    print(f"{'=' * 70}")

    try:
        records = parse_company(
            company,
            company_output,
        )

        if not records:
            raise RuntimeError(
                f"Nenhum veículo extraído para '{name}'. "
                f"Parser usado: {parser}. "
                f"Se o site for dinâmico, tente parser='playwright'."
            )

        df = build_dataframe(records)

        logging.info(
            "%s: veículos extraídos=%d",
            name,
            len(df),
        )

        brands = ranking_marcas(df)
        models = ranking_modelos(df)

        min_stock = int(
            company.get(
                "min_model_stock",
                4,
            )
        )

        classified = classify_content(
            models,
            min_model_stock=min_stock,
        )

        export_files(
            company_name=name,
            df=df,
            brands=brands,
            classified=classified,
            output_dir=company_output,
            source_url=url,
            parser=parser,
        )

        print(f"OK: {len(df)} veículos")
        print(f"Output: {company_output.resolve()}")

        print("\nTop modelos:")

        print(
            classified.head(10)[
                [
                    "marca",
                    "modelo",
                    "estoque",
                    "preco_min",
                    "preco_max",
                    "categoria_conteudo",
                ]
            ].to_string(index=False)
        )

        return True

    except Exception as exc:
        message = str(exc)

        logging.exception(
            "Falha na empresa %s: %s",
            name,
            message,
        )

        save_error(
            company_name=name,
            company_output=company_output,
            message=message,
        )

        print(
            f"ERRO: {message} | "
            f"veículos=0 | "
            f"output={company_output}"
        )

        if debug:
            print(
                "\nModo debug ativo. "
                "Confira os arquivos dentro da pasta da empresa."
            )

        return False


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Scraper multiempresa de estoque "
            "e gerador automático de briefing."
        )
    )

    parser.add_argument(
        "--config",
        default="config.json",
        help="Arquivo JSON de configuração.",
    )

    parser.add_argument(
        "--url",
        help=(
            "Compatibilidade: URL de uma empresa "
            "quando não estiver usando config multiempresa."
        ),
    )

    parser.add_argument(
        "--out",
        default=None,
        help="Diretório raiz de saída.",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Ativa logs detalhados.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    try:
        config_path = Path(args.config)
        config = load_config(config_path)

        if args.url:
            config["empresas"] = [
                {
                    "nome": "Azul Premium",
                    "url": args.url,
                    "parser": "auto",
                    "min_model_stock": 4,
                }
            ]

        root_output = Path(
            args.out
            if args.out
            else config.get(
                "output_dir",
                DEFAULT_OUTPUT,
            )
        )

        empresas = config.get("empresas", [])

        if not empresas:
            raise RuntimeError(
                "Nenhuma empresa foi encontrada no config.json."
            )

        success = 0
        failed = 0

        for company in empresas:
            if not company.get("nome"):
                logging.error(
                    "Empresa ignorada: campo 'nome' ausente."
                )
                failed += 1
                continue

            if not company.get("url"):
                logging.error(
                    "Empresa '%s' ignorada: campo 'url' ausente.",
                    company.get("nome"),
                )
                failed += 1
                continue

            if process_company(
                company,
                root_output,
                debug=args.debug,
            ):
                success += 1
            else:
                failed += 1

        print("\n" + "=" * 70)
        print("RESUMO DA EXECUÇÃO")
        print("=" * 70)
        print(f"Empresas OK   : {success}")
        print(f"Empresas erro : {failed}")
        print(f"Output        : {root_output.resolve()}")

        if failed:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nExecução interrompida pelo usuário.")
        sys.exit(130)

    except requests.RequestException as exc:
        logging.error(
            "Erro de acesso HTTP: %s",
            exc,
        )
        sys.exit(2)

    except Exception as exc:
        logging.exception(
            "Falha geral: %s",
            exc,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
