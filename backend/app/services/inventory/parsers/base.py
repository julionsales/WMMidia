"""Contrato comum dos parsers de estoque (um módulo por site)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from bs4 import BeautifulSoup

from app.services.inventory.normalize import RawVehicle, clean_text


@dataclass
class ParseResult:
    vehicles: list[RawVehicle] = field(default_factory=list)
    declared_total: int | None = None  # total anunciado pelo site, quando existe
    pages_fetched: int = 0
    pages_failed: int = 0
    reached_end: bool = True  # False quando o limite de páginas interrompeu a coleta
    final_url: str | None = None
    warnings: list[str] = field(default_factory=list)


class Fetchers(Protocol):
    http: object
    browser: object | None


class InventoryParser(Protocol):
    key: str
    label: str
    requires_browser: bool

    def collect(self, url: str, fetchers: Fetchers, options: dict) -> ParseResult: ...


def soup_of(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001 - lxml ausente em ambiente local
        return BeautifulSoup(html, "html.parser")


def text_of(node) -> str:
    return clean_text(node.get_text(" ", strip=True)) if node is not None else ""


COUNT_RE = re.compile(r"(\d{1,6})\s+(?:ve[ií]culos?|resultados?|an[uú]ncios?)\s+encontrad", re.I)
