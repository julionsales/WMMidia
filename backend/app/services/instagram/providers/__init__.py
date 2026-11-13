"""Fábrica de provedores do Instagram."""

from __future__ import annotations

from app.core.config import Settings
from app.services.instagram.providers.base import InstagramProvider, OfficialGraphApiProvider


def get_provider(settings: Settings) -> InstagramProvider:
    if settings.instagram_provider == "official_api":
        return OfficialGraphApiProvider()
    from app.services.instagram.providers.instaloader_provider import InstaloaderProvider

    return InstaloaderProvider(
        session_file=settings.instagram_session_file,
        session_username=settings.instagram_session_username,
    )
