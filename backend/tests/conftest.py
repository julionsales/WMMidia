import os
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-only-for-automated-tests-000")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, url, text):
        self.url, self.text, self.status = url, text, 200


class FakeHttp:
    """Substitui o HttpFetcher nos testes: devolve fixtures, sem rede."""

    def __init__(self, pages: dict, fail_on: set | None = None):
        self.pages, self.fail_on, self.calls = pages, fail_on or set(), []

    def _resolve(self, key, url):
        self.calls.append(key)
        if key in self.fail_on:
            from app.services.inventory.fetchers import FetchError

            raise FetchError("falha simulada", transient=True)
        return FakeResponse(url, self.pages[key])

    def get(self, url, **_):
        return self._resolve(url, url)

    def post(self, url, data=None, **_):
        return self._resolve(f"{url}#{data.get('pagina')}", url)


@pytest.fixture
def fixture():
    return fixture_text


def pytest_collection_modifyitems(config, items):
    if os.environ.get("TEST_MONGO_URI"):
        return
    skip = pytest.mark.skip(reason="defina TEST_MONGO_URI para testes com MongoDB real")
    for item in items:
        if "mongo" in item.keywords:
            item.add_marker(skip)
