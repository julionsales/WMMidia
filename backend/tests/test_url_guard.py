import pytest

from app.core.logging import redact
from app.core.url_guard import UnsafeUrlError, check_url_syntax, validate_public_url
from app.services.inventory.fetchers import FetchError, HttpFetcher


def public_resolver(host, port):
    return ["93.184.216.34"]


def private_resolver(host, port):
    return ["10.0.0.5"]


@pytest.mark.parametrize("url", [
    "http://localhost/estoque",
    "http://127.0.0.1/",
    "http://10.1.2.3/",
    "http://192.168.0.10/",
    "http://172.16.5.4/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://0.0.0.0/",
    "http://mongo:27017/",
    "http://servidor.internal/",
    "ftp://site.com.br/",
    "file:///etc/passwd",
    "https://user:senha@site.com.br/",
    "https://site.com.br:6379/",
    "http://intranet/",
])
def test_blocks_internal_destinations(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url, resolver=public_resolver)


def test_blocks_public_name_resolving_to_private_ip():
    with pytest.raises(UnsafeUrlError):
        validate_public_url("https://loja.com.br/estoque", resolver=private_resolver)


def test_accepts_public_url():
    assert validate_public_url("https://azulpremium.com.br/Veiculos", resolver=public_resolver)
    assert check_url_syntax("https://site.com.br:443/x")[0] == "site.com.br"


class FakeRaw:
    connection = None


class FakeResp:
    def __init__(self, status, location=None, body=b"ok"):
        self.status_code = status
        self.headers = {"Location": location} if location else {}
        self.is_redirect = status in (301, 302, 303, 307, 308)
        self.encoding = "utf-8"
        self.raw = FakeRaw()
        self._body = body

    def iter_content(self, _):
        yield self._body

    def close(self):
        pass


class FakeSession:
    trust_env = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def request(self, method, url, **_):
        self.urls.append(url)
        return self.responses.pop(0)


def guard(url):
    """Validador de teste: domínio 'interno.exemplo' resolve para IP privado."""
    resolver = private_resolver if "interno.exemplo" in url else public_resolver
    return validate_public_url(url, resolver=resolver)


def test_redirect_to_internal_destination_is_blocked():
    session = FakeSession([FakeResp(302, "http://169.254.169.254/latest/meta-data/")])
    fetcher = HttpFetcher(validator=guard, session=session)
    with pytest.raises(FetchError, match="bloqueado"):
        fetcher.get("https://loja.com.br/estoque")
    assert session.urls == ["https://loja.com.br/estoque"]  # o destino interno nunca é acessado


def test_redirect_to_name_resolving_privately_is_blocked():
    session = FakeSession([FakeResp(301, "https://interno.exemplo/admin")])
    with pytest.raises(FetchError):
        HttpFetcher(validator=guard, session=session).get("https://loja.com.br/")


def test_safe_redirect_is_followed():
    session = FakeSession([FakeResp(301, "/novo"), FakeResp(200, body="<html>ok</html>".encode())])
    resp = HttpFetcher(validator=guard, session=session).get("https://loja.com.br/velho")
    assert resp.url == "https://loja.com.br/novo" and "ok" in resp.text


def test_server_errors_are_transient():
    with pytest.raises(FetchError) as info:
        HttpFetcher(validator=guard, session=FakeSession([FakeResp(503)])).get("https://loja.com.br/")
    assert info.value.transient is True


def test_redact_secrets_in_logs():
    text = redact("cookie: sessionid=abc123; csrftoken=xyz mongodb://app:segredo@mongo:27017 Authorization: Bearer eyJhbGciOi.x.y")
    assert "abc123" not in text and "xyz" not in text and "segredo" not in text and "eyJhbGciOi" not in text
