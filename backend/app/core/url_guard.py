"""Validação de URLs de coleta contra acesso a destinos internos (SSRF).

Regras:
- apenas http/https, sem credenciais embutidas na URL;
- portas permitidas: padrão (80/443) ou 8080/8443;
- nomes como localhost, *.local, *.internal, *.localhost bloqueados;
- todo endereço resolvido (IPv4 e IPv6) precisa ser público/global;
- a mesma verificação é aplicada a cada redirecionamento (ver app.services.inventory.fetchers).

Limitação documentada: entre a resolução DNS e a conexão existe uma janela (DNS rebinding).
O fetcher HTTP mitiga verificando também o IP efetivamente conectado.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443, 8080, 8443}
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".corp", ".intranet")
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "mongo",
    "mongodb",
    "redis",
    "api",
    "worker",
    "scheduler",
    "frontend",
}


class UnsafeUrlError(ValueError):
    """URL aponta para destino não permitido."""


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def check_url_syntax(url: str) -> tuple[str, int | None]:
    """Validação sem DNS. Retorna (hostname, porta)."""
    if not url or len(url) > 2048:
        raise UnsafeUrlError("URL vazia ou longa demais.")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError("URL malformada.") from exc
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("Somente URLs http:// ou https:// são aceitas.")
    if parts.username or parts.password:
        raise UnsafeUrlError("URLs com credenciais embutidas não são aceitas.")
    host = (parts.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise UnsafeUrlError("URL sem domínio.")
    if port not in ALLOWED_PORTS:
        raise UnsafeUrlError("Porta não permitida para coleta.")
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise UnsafeUrlError("Domínio interno não permitido.")
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip:
        if not is_public_ip(host):
            raise UnsafeUrlError("Endereço IP privado, local ou reservado não permitido.")
    elif "." not in host:
        raise UnsafeUrlError("Domínio sem extensão pública não permitido.")
    return host, port


def resolve_host(host: str, port: int | None) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Não foi possível resolver o domínio {host}.") from exc
    return sorted({info[4][0] for info in infos})


def validate_public_url(url: str, resolver=resolve_host) -> str:
    """Validação completa (sintaxe + DNS). Retorna a URL normalizada."""
    host, port = check_url_syntax(url)
    addresses = resolver(host, port)
    if not addresses:
        raise UnsafeUrlError(f"O domínio {host} não resolveu para nenhum endereço.")
    blocked = [a for a in addresses if not is_public_ip(a)]
    if blocked:
        raise UnsafeUrlError(f"O domínio {host} resolve para endereço interno ou reservado.")
    return url.strip()
