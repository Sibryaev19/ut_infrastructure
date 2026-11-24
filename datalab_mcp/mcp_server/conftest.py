"""Общие помощники тестов: настройки, фейковый клиент datalab."""
from __future__ import annotations

import httpx

from src.config import Settings
from src.datalab import ToolResponse


def make_settings(**overrides) -> Settings:
    values = {
        "datalab_url": "https://datalab.test/9999",
        "datalab_token": "secret-token",
        "verify_tls": False,
        "timeout": 120.0,
        "connect_timeout": 10.0,
    }
    values.update(overrides)
    return Settings(**values)


def make_http_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class FakeClient:
    """Замена DatalabClient: запоминает вызовы, не ходит в сеть."""

    def __init__(self, text: str = "ok", error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict, float | None]] = []
        self._text = text
        self._error = error

    async def call(self, tool, payload, timeout=None) -> ToolResponse:
        self.calls.append((tool, dict(payload), timeout))
        if self._error is not None:
            raise self._error
        return ToolResponse(text=self._text, meta={})
