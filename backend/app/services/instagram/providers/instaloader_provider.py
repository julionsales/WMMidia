"""Provedor baseado em Instaloader para perfis públicos.

Sem garantia de funcionamento: o Instagram pode exigir login, limitar consultas, ocultar
métricas ou mudar a estrutura a qualquer momento. Todas essas situações são tratadas
como resultados esperados (status failed/partial com código de erro), nunca contornadas.

Sessão opcional: um arquivo de sessão do Instaloader gerado pela própria equipe
(conta de consulta, nunca a senha da empresa monitorada) pode ser montado no worker
via INSTAGRAM_SESSION_FILE. O conteúdo do arquivo nunca é registrado em log.
"""

from __future__ import annotations

import logging
from datetime import timezone

from app.core.logging import redact
from app.services.instagram.providers.base import (
    InstagramProvider,
    PostData,
    ProfileData,
    ProfileFetchResult,
)

log = logging.getLogger(__name__)


def _format_of(post) -> str:
    typename = getattr(post, "typename", None)
    if typename == "GraphSidecar":
        return "carrossel"
    if typename == "GraphImage":
        return "imagem"
    if typename == "GraphVideo":
        try:
            if getattr(post, "product_type", None) == "clips":
                return "reels"
        except Exception:  # noqa: BLE001 - campo nem sempre presente
            pass
        return "video"
    return "desconhecido"


def _likes_of(post) -> tuple[int | None, bool]:
    node = getattr(post, "_node", {}) or {}
    if node.get("like_and_view_counts_disabled"):
        return None, True
    try:
        likes = post.likes
    except Exception:  # noqa: BLE001
        return None, False
    if likes is None or likes < 0:
        return None, False
    return int(likes), False


def _is_pinned(post) -> bool:
    try:
        return bool(getattr(post, "is_pinned", False))
    except Exception:  # noqa: BLE001
        return False


def _comments_of(post) -> int | None:
    try:
        value = post.comments
    except Exception:  # noqa: BLE001
        return None
    return int(value) if value is not None and value >= 0 else None


MAX_PINNED = 3


def mark_pinned_by_order(posts: list[PostData]) -> None:
    """Fallback quando a API não informa fixação: o feed vem em ordem decrescente de data,
    então um dos primeiros itens mais antigo que algum item posterior está fora de ordem
    (fixado no topo do perfil)."""
    for i, post in enumerate(posts[:MAX_PINNED]):
        if not post.is_pinned and any(later.taken_at > post.taken_at for later in posts[i + 1:]):
            post.is_pinned = True


class InstaloaderProvider(InstagramProvider):
    name = "instaloader"
    description = "Instaloader (dados públicos acessíveis, sem garantia)"

    def __init__(self, session_file: str | None = None, session_username: str | None = None,
                 request_timeout: float = 30.0):
        self.session_file = session_file
        self.session_username = session_username
        self.request_timeout = request_timeout

    def _loader(self):
        import instaloader

        loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
            max_connection_attempts=1,
            request_timeout=self.request_timeout,
        )
        if self.session_file and self.session_username:
            loader.load_session_from_file(self.session_username, self.session_file)
        return loader

    def fetch_profile(self, username: str, posts_limit: int) -> ProfileFetchResult:
        try:
            import instaloader
            from instaloader import exceptions as ex
        except ImportError:
            return ProfileFetchResult(status="failed", source=self.name, error_code="provider_unavailable",
                                      error_message="Instaloader não instalado")

        too_many = getattr(ex, "TooManyRequestsException", ())
        result = ProfileFetchResult(status="failed", source=self.name, posts_requested=posts_limit)

        def classify(exc: Exception) -> None:
            message = redact(str(exc))[:240]
            result.error_message = message
            lowered = message.lower()
            if too_many and isinstance(exc, too_many) or "429" in lowered or "please wait a few minutes" in lowered:
                result.error_code, result.retryable = "rate_limited", True
            elif isinstance(exc, ex.LoginRequiredException) or "login" in lowered:
                result.error_code = "login_required"
            elif isinstance(exc, ex.PrivateProfileNotFollowedException):
                result.error_code = "private_profile"
            elif isinstance(exc, ex.ProfileNotExistsException):
                result.error_code = "not_found"
            elif isinstance(exc, (ex.QueryReturnedForbiddenException,)):
                result.error_code = "blocked"
            elif isinstance(exc, ex.ConnectionException):
                result.error_code, result.retryable = "connection", True
            else:
                result.error_code = "unknown"

        try:
            loader = self._loader()
            profile = instaloader.Profile.from_username(loader.context, username)
            result.profile = ProfileData(
                username=profile.username,
                full_name=profile.full_name or None,
                biography=profile.biography or None,
                followers=profile.followers,
                following=profile.followees,
                media_count=profile.mediacount,
                is_private=profile.is_private,
                external_id=str(profile.userid),
            )
        except Exception as exc:  # noqa: BLE001 - classificado em códigos esperados
            classify(exc)
            log.info("Instagram @%s: falha (%s)", username, result.error_code)
            return result

        if profile.is_private:
            result.status = "partial"
            result.error_code = "private_profile"
            result.notes.append("Perfil privado: apenas dados do perfil disponíveis")
            return result

        try:
            # Fixados aparecem primeiro e podem ser antigos: lê alguns itens a mais e
            # depois descarta o excedente de não fixados.
            for index, post in enumerate(profile.get_posts()):
                if index >= posts_limit + MAX_PINNED:
                    break
                pinned = _is_pinned(post)
                likes, hidden = _likes_of(post)
                fmt = _format_of(post)
                path = "reel" if fmt == "reels" else "p"
                result.posts.append(
                    PostData(
                        shortcode=post.shortcode,
                        url=f"https://www.instagram.com/{path}/{post.shortcode}/",
                        taken_at=post.date_utc.replace(tzinfo=timezone.utc),
                        caption=(post.caption or None),
                        format=fmt,  # type: ignore[arg-type]
                        likes=likes,
                        comments=_comments_of(post),
                        external_id=str(post.mediaid),
                        likes_hidden=hidden,
                        is_pinned=pinned,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            classify(exc)
            result.status = "partial"
            mark_pinned_by_order(result.posts)
            result.notes.append(
                f"Lista de publicações interrompida após {len(result.posts)} item(ns) ({result.error_code})"
            )
            return result

        mark_pinned_by_order(result.posts)
        kept, recent = [], 0
        for post in result.posts:
            if post.is_pinned or recent < posts_limit:
                kept.append(post)
                recent += 0 if post.is_pinned else 1
        result.posts = kept

        result.status = "success"
        result.error_code = None
        result.error_message = None
        if any(p.likes is None for p in result.posts):
            result.notes.append("Algumas publicações não exibem curtidas publicamente")
        return result
