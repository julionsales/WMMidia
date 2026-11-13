"""Acesso HTTP e navegador com validação de destino em cada salto.

Executado somente no worker (código síncrono). A API nunca faz coleta.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urljoin, urlsplit

import requests

from app.core.url_guard import UnsafeUrlError, is_public_ip, validate_public_url

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36 MonitorAutomotivo/1.0"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class FetchError(Exception):
    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


@dataclass
class FetchResponse:
    url: str
    status: int
    text: str


class HttpFetcher:
    """requests com redirecionamentos manuais: cada salto é validado contra SSRF."""

    def __init__(self, timeout: int = 30, max_redirects: int = 5, max_bytes: int = 15_000_000,
                 validator=validate_public_url, session: requests.Session | None = None):
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.max_bytes = max_bytes
        self.validator = validator
        self.session = session or requests.Session()
        self.session.trust_env = False  # ignora proxies do ambiente
        self.requests_made = 0

    def get(self, url: str, **kw) -> FetchResponse:
        return self.request("GET", url, **kw)

    def post(self, url: str, data: dict | None = None, **kw) -> FetchResponse:
        return self.request("POST", url, data=data, **kw)

    def request(self, method: str, url: str, data: dict | None = None, headers: dict | None = None) -> FetchResponse:
        current = url
        for _hop in range(self.max_redirects + 1):
            try:
                self.validator(current)
            except UnsafeUrlError as exc:
                raise FetchError(f"Destino bloqueado: {exc}") from exc
            try:
                self.requests_made += 1
                resp = self.session.request(
                    method,
                    current,
                    data=data,
                    headers={**DEFAULT_HEADERS, **(headers or {})},
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=True,
                )
            except requests.Timeout as exc:
                raise FetchError("Tempo esgotado ao acessar o site", transient=True) from exc
            except requests.ConnectionError as exc:
                raise FetchError("Falha de conexão com o site", transient=True) from exc
            except requests.RequestException as exc:
                raise FetchError(f"Erro HTTP: {type(exc).__name__}") from exc

            self._check_peer(resp)
            if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                resp.close()
                if not location:
                    raise FetchError("Redirecionamento sem destino")
                current = urljoin(current, location)
                if resp.status_code in (301, 302, 303):
                    method, data = "GET", None
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                resp.close()
                raise FetchError(f"Site respondeu {resp.status_code}", transient=True)
            if resp.status_code >= 400:
                resp.close()
                raise FetchError(f"Site respondeu {resp.status_code}")

            body = b""
            for chunk in resp.iter_content(64 * 1024):
                body += chunk
                if len(body) > self.max_bytes:
                    resp.close()
                    raise FetchError("Resposta maior que o limite configurado")
            encoding = resp.encoding if resp.encoding and resp.encoding.lower() != "iso-8859-1" else None
            text = body.decode(encoding or _sniff_encoding(body), errors="replace")
            return FetchResponse(url=current, status=resp.status_code, text=text)
        raise FetchError("Redirecionamentos demais")

    @staticmethod
    def _check_peer(resp: requests.Response) -> None:
        """Melhor esforço contra DNS rebinding: confere o IP efetivamente conectado."""
        try:
            sock = resp.raw.connection.sock  # type: ignore[union-attr]
            peer = sock.getpeername()[0]
        except Exception:  # noqa: BLE001 - nem sempre disponível (ex.: proxies, mocks)
            return
        if not is_public_ip(peer):
            resp.close()
            raise FetchError("Conexão resolvida para endereço interno; acesso bloqueado")


def _sniff_encoding(body: bytes) -> str:
    head = body[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset=[\"']?([A-Za-z0-9_\-]+)", head)
    return match.group(1) if match else "utf-8"


@lru_cache(maxsize=512)
def _host_allowed(scheme: str, host: str, port: int | None) -> bool:
    try:
        netloc = host if port is None else f"{host}:{port}"
        validate_public_url(f"{scheme}://{netloc}/")
        return True
    except UnsafeUrlError:
        return False


def url_allowed(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme in ("data", "blob", "about"):
        return True
    if parts.scheme not in ("http", "https"):
        return False
    try:
        port = parts.port
    except ValueError:
        return False
    return _host_allowed(parts.scheme, (parts.hostname or "").lower(), port)


class BrowserFetcher:
    """Renderiza páginas com JavaScript (Playwright/Chromium), bloqueando destinos internos."""

    LOAD_MORE_RE = re.compile(r"^\s*(carregar|mostrar|exibir)\s+mais", re.I)

    def __init__(self, timeout_ms: int = 45_000):
        self.timeout_ms = timeout_ms

    def render(self, url: str, load_more: bool = False, max_clicks: int = 20) -> FetchResponse:
        try:
            validate_public_url(url)
        except UnsafeUrlError as exc:
            raise FetchError(f"Destino bloqueado: {exc}") from exc
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeout
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - imagem sem Playwright
            raise FetchError("Playwright não está instalado neste serviço") from exc

        def guard(route):
            req = route.request
            if req.resource_type in ("image", "media", "font"):
                return route.abort()
            if not url_allowed(req.url):
                log.warning("Requisição do navegador bloqueada para destino não permitido")
                return route.abort()
            return route.continue_()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
                try:
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1000},
                        locale="pt-BR",
                        user_agent=USER_AGENT,
                        service_workers="block",
                        accept_downloads=False,
                    )
                    context.route("**/*", guard)
                    page = context.new_page()
                    response = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                    # Redirecionamentos de navegação não passam pelo route(): validação explícita.
                    req = response.request if response else None
                    while req is not None:
                        if not url_allowed(req.url):
                            raise FetchError("Redirecionamento para destino não permitido")
                        req = req.redirected_from
                    if response and response.status >= 400:
                        raise FetchError(f"Site respondeu {response.status}", transient=response.status >= 500 or response.status == 429)
                    page.wait_for_timeout(3000)
                    if load_more:
                        self._click_load_more(page, max_clicks)
                    page.wait_for_timeout(1000)
                    if not url_allowed(page.url):
                        raise FetchError("Página final em destino não permitido")
                    return FetchResponse(url=page.url, status=response.status if response else 0, text=page.content())
                finally:
                    browser.close()
        except FetchError:
            raise
        except PlaywrightTimeout as exc:
            raise FetchError("Tempo esgotado ao renderizar a página", transient=True) from exc
        except PlaywrightError as exc:
            raise FetchError(f"Falha no navegador: {str(exc).splitlines()[0][:160]}", transient=True) from exc

    def _click_load_more(self, page, max_clicks: int) -> None:
        for _ in range(max_clicks):
            page.mouse.wheel(0, 20000)
            page.wait_for_timeout(800)
            buttons = page.get_by_role("button", name=self.LOAD_MORE_RE)
            if buttons.count() == 0:
                buttons = page.locator("a, button").filter(has_text=self.LOAD_MORE_RE)
            clicked = False
            for i in range(min(buttons.count(), 5)):
                button = buttons.nth(i)
                try:
                    if button.is_visible():
                        href = button.get_attribute("href")
                        if href and not href.startswith("#") and not href.startswith("javascript"):
                            continue  # evita navegar para outra página
                        button.click(timeout=2500)
                        page.wait_for_timeout(1500)
                        clicked = True
                        break
                except Exception:  # noqa: BLE001
                    continue
            if not clicked:
                break
