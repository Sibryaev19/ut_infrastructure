"""Настройки MCP-сервера: читаются из .env и окружения.

В отличие от сервера на datalab, здесь .env уместен: это машина пользователя.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from dotenv import load_dotenv


class ConfigError(Exception):
    """Не хватает обязательной настройки: сервер не может работать."""


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


@dataclass(frozen=True)
class Settings:
    datalab_url: str
    datalab_token: str
    verify_tls: bool = False
    timeout: float = 120.0
    connect_timeout: float = 10.0

    def tool_url(self, tool: str) -> str:
        return f"{self.datalab_url}/tools/{tool}"

    def request_timeout(self, total: float | None = None) -> "httpx.Timeout":
        """Общий таймаут запроса с коротким connect: «datalab недоступен» не должен висеть."""
        import httpx

        return httpx.Timeout(total if total is not None else self.timeout, connect=self.connect_timeout)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = os.environ

    url = (env.get("DATALAB_URL") or "").strip().rstrip("/")
    if not url:
        raise ConfigError(
            "DATALAB_URL is not set. Пример: DATALAB_URL=https://<адрес datalab>/<порт>"
        )
    if not url.startswith(("http://", "https://")):
        raise ConfigError(f"DATALAB_URL must start with http:// or https://: {url!r}")

    token = (env.get("DATALAB_TOKEN") or "").strip()
    if not token:
        raise ConfigError("DATALAB_TOKEN is not set (JUPYTERHUB_API_TOKEN)")

    try:
        timeout = float(env.get("HTTP_TIMEOUT") or 120)
    except ValueError as exc:
        raise ConfigError(f"HTTP_TIMEOUT must be a number: {env.get('HTTP_TIMEOUT')!r}") from exc

    return Settings(
        datalab_url=url,
        datalab_token=token,
        verify_tls=_as_bool(env.get("VERIFY_TLS"), default=False),
        timeout=timeout,
        connect_timeout=10.0,
    )
