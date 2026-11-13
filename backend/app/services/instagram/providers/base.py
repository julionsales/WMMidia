"""Contrato dos provedores de dados do Instagram.

Indicadores e telas dependem apenas destes tipos; trocar a origem (Instaloader, API
oficial autorizada, entrada manual) não exige mudar o restante do sistema.

Convenção: `None` significa "indisponível" (não coletado / oculto); 0 é zero de fato.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

FetchStatus = Literal["success", "partial", "failed"]
ErrorCode = Literal[
    "login_required", "private_profile", "not_found", "rate_limited", "blocked",
    "connection", "provider_unavailable", "unknown",
]
PostFormat = Literal["imagem", "video", "reels", "carrossel", "desconhecido"]


@dataclass
class ProfileData:
    username: str
    full_name: str | None = None
    biography: str | None = None
    followers: int | None = None
    following: int | None = None
    media_count: int | None = None
    is_private: bool | None = None
    external_id: str | None = None


@dataclass
class PostData:
    shortcode: str
    url: str
    taken_at: datetime
    caption: str | None = None
    format: PostFormat = "desconhecido"
    likes: int | None = None
    comments: int | None = None
    external_id: str | None = None
    likes_hidden: bool = False
    is_pinned: bool = False


@dataclass
class ProfileFetchResult:
    status: FetchStatus
    source: str
    profile: ProfileData | None = None
    posts: list[PostData] = field(default_factory=list)
    posts_requested: int = 0
    error_code: ErrorCode | None = None
    error_message: str | None = None
    notes: list[str] = field(default_factory=list)
    retryable: bool = False


class InstagramProvider(ABC):
    name: str = "base"
    description: str = ""

    @abstractmethod
    def fetch_profile(self, username: str, posts_limit: int) -> ProfileFetchResult:
        """Coleta dados públicos acessíveis. Nunca segue, curte, comenta ou envia mensagens."""


class OfficialGraphApiProvider(InstagramProvider):
    """Ponto de extensão para integração AUTORIZADA com a API oficial (fora do MVP).

    Exigirá token do próprio cliente via fluxo de autorização da Meta; métricas como
    alcance e salvamentos só seriam exibidas a partir dessa origem.
    """

    name = "official_api"
    description = "API oficial (não incluída no MVP)"

    def fetch_profile(self, username: str, posts_limit: int) -> ProfileFetchResult:
        return ProfileFetchResult(
            status="failed",
            source=self.name,
            error_code="provider_unavailable",
            error_message="Integração com a API oficial ainda não implementada neste MVP",
        )
