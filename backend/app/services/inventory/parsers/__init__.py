"""Registro de parsers de estoque. Para adicionar um site, crie um módulo e registre aqui."""

from __future__ import annotations

from urllib.parse import urlsplit

from app.services.inventory.parsers.avance import AvanceParser
from app.services.inventory.parsers.azul import AzulParser
from app.services.inventory.parsers.generic import GenericParser, PlaywrightParser
from app.services.inventory.parsers.hazul import HazulParser

PARSERS = {p.key: p for p in (AzulParser(), HazulParser(), AvanceParser(), GenericParser(), PlaywrightParser())}

DOMAIN_HINTS = {
    "azulpremium.com.br": "azul",
    "grupohazul.com.br": "hazul",
    "avancepremium.com.br": "avance",
}


def resolve_parser_key(parser: str | None, url: str | None) -> str:
    parser = (parser or "auto").lower()
    if parser != "auto":
        if parser not in PARSERS:
            raise ValueError(f"Parser desconhecido: {parser}")
        return parser
    host = (urlsplit(url or "").hostname or "").lower()
    for domain, key in DOMAIN_HINTS.items():
        if host == domain or host.endswith("." + domain):
            return key
    return "generic"


def get_parser(parser: str | None, url: str | None):
    return PARSERS[resolve_parser_key(parser, url)]


def parser_catalog() -> list[dict]:
    return [{"key": "auto", "label": "Automático (pelo domínio)", "requires_browser": False}] + [
        {"key": p.key, "label": p.label, "requires_browser": p.requires_browser} for p in PARSERS.values()
    ]
