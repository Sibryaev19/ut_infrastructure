"""Переиспользуемый async-клиент datalab.

Без импортов MCP: модуль можно тащить в другие проекты.
Транспорт тонкий — один POST на тул, вся логика на сервере datalab.

Использование:
    settings = load_settings()
    async with DatalabClient(settings) as client:
        response = await client.call("read_file", {"path": "/abs/file.py"})
        print(response.text, response.meta)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from .errors import DatalabError, DatalabTransportError
from ..config import Settings


@dataclass
class ToolResponse:
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


class DatalabClient:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(verify=settings.verify_tls)

    def _headers(self) -> dict[str, str]:
        # Токен проверяет платформа datalab, не наш сервер.
        return {"Authorization": f"token {self._settings.datalab_token}"}

    async def call(
        self,
        tool: str,
        payload: dict[str, Any],
        timeout: float | None = None,
    ) -> ToolResponse:
        url = self._settings.tool_url(tool)
        try:
            response = await self._client.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self._settings.request_timeout(timeout),
            )
        except httpx.TimeoutException as exc:
            raise DatalabTransportError(
                "timeout",
                f"datalab did not answer within {timeout or self._settings.timeout:.0f}s: {url}",
                "Проверьте, что сервер на datalab запущен. Для долгих команд "
                "увеличьте timeout_ms (клиент подождёт timeout_ms + 30 с).",
            ) from exc
        except httpx.HTTPError as exc:
            raise DatalabTransportError(
                "connection",
                f"cannot reach datalab at {url}: {exc}",
                "Проверьте DATALAB_URL, сеть и что сервер на datalab запущен.",
            ) from exc

        if response.status_code >= 400:
            raise _error_from_response(response, url)

        try:
            data = response.json()
        except ValueError as exc:
            raise DatalabError(
                "bad_response",
                f"datalab returned non-JSON response (HTTP {response.status_code})",
                f"Первые 200 символов: {response.text[:200]!r}",
                status=response.status_code,
            ) from exc

        if not isinstance(data, dict) or "error" in data or "text" not in data:
            raise DatalabError(
                "bad_response",
                "datalab returned an unexpected payload",
                f"DATALAB_URL должен указывать на agent_server. Тело: {str(data)[:200]}",
                status=response.status_code,
            )

        return ToolResponse(text=str(data.get("text", "")), meta=dict(data.get("meta") or {}))

    async def info(self) -> dict[str, Any]:
        return (await self.call("workspace_info", {})).meta

    async def health(self) -> bool:
        try:
            response = await self._client.get(
                f"{self._settings.datalab_url}/health",
                headers=self._headers(),
                timeout=self._settings.request_timeout(10.0),
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "DatalabClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


def _error_from_response(response: httpx.Response, url: str) -> DatalabError:
    try:
        data = response.json()
    except ValueError:
        return DatalabError(
            "http_error",
            f"HTTP {response.status_code} from {url}",
            f"Тело ответа: {response.text[:200]!r}",
            status=response.status_code,
        )

    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return DatalabError(
            code=str(error.get("code") or "http_error"),
            message=str(error.get("message") or f"HTTP {response.status_code}"),
            hint=error.get("hint"),
            status=response.status_code,
        )

    detail = data.get("detail") if isinstance(data, dict) else None
    return DatalabError(
        "http_error",
        f"HTTP {response.status_code}: {detail if detail is not None else str(data)[:200]}",
        hint=None,
        status=response.status_code,
    )
