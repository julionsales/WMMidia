"""Normalizações de entrada usadas no cadastro."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

USERNAME_RE = re.compile(r"^[a-z0-9._]{1,30}$")
RESERVED_PATHS = {"p", "reel", "reels", "explore", "stories", "accounts", "tv", "direct"}


def normalize_instagram_username(value: str | None) -> str | None:
    """Aceita '@perfil', 'perfil', 'instagram.com/perfil' ou URL completa."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if "instagram.com" in raw.lower() or raw.lower().startswith(("http://", "https://")):
        if not raw.lower().startswith(("http://", "https://")):
            raw = "https://" + raw
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        if host not in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
            raise ValueError("A URL informada não é do Instagram.")
        segments = [s for s in parts.path.split("/") if s]
        if not segments or segments[0].lower() in RESERVED_PATHS:
            raise ValueError("Não foi possível identificar o perfil na URL do Instagram.")
        raw = segments[0]
    username = raw.lstrip("@").strip().lower()
    if not USERNAME_RE.match(username) or username.startswith(".") or username.endswith(".") or ".." in username:
        raise ValueError("Username do Instagram inválido.")
    return username


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "empresa"
