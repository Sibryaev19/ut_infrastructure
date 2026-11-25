"""Обработчики тулов: payload -> DatalabClient.call -> текст для агента.

Здесь нет правил путей и нет MCP: только сопоставление аргументов и вызов.
Ошибки клиента (DatalabError / DatalabTransportError) пробрасываются наверх,
их превращает в isError слой tools/registration.py.
"""
from __future__ import annotations

from typing import Any

from ..datalab import DatalabClient


class Handlers:
    def __init__(self, client: DatalabClient) -> None:
        self._client = client

    async def _call(self, tool: str, payload: dict[str, Any], timeout: float | None = None) -> str:
        response = await self._client.call(tool, payload, timeout=timeout)
        return response.text

    async def workspace_info(self) -> str:
        return await self._call("workspace_info", {})

    async def list_dir(self, *, path: str) -> str:
        return await self._call("list_dir", {"path": path})

    async def read_file(self, *, path: str, offset: int = 1, limit: int = 2000) -> str:
        return await self._call("read_file", {"path": path, "offset": offset, "limit": limit})

    async def write_file(
        self,
        *,
        path: str,
        content: str,
        expected_mtime_ms: int | None = None,
    ) -> str:
        return await self._call(
            "write_file",
            {"path": path, "content": content, "expected_mtime_ms": expected_mtime_ms},
        )

    async def edit_file(
        self,
        *,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        expected_mtime_ms: int | None = None,
    ) -> str:
        return await self._call(
            "edit_file",
            {
                "path": path,
                "old_string": old_string,
                "new_string": new_string,
                "replace_all": replace_all,
                "expected_mtime_ms": expected_mtime_ms,
            },
        )

    async def glob(self, *, pattern: str, path: str, limit: int = 100) -> str:
        return await self._call("glob", {"pattern": pattern, "path": path, "limit": limit})

    async def grep(
        self,
        *,
        pattern: str,
        path: str,
        include: str | None = None,
        literal: bool = False,
        limit: int = 100,
    ) -> str:
        return await self._call(
            "grep",
            {
                "pattern": pattern,
                "path": path,
                "include": include,
                "literal": literal,
                "limit": limit,
            },
        )

    async def bash(
        self,
        *,
        command: str,
        workdir: str,
        timeout_ms: int = 120_000,
        description: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "command": command,
            "workdir": workdir,
            "timeout_ms": timeout_ms,
        }
        if description:
            payload["description"] = description
        # Клиент ждёт на 30 с дольше сервера, иначе оборвёт команду раньше таймаута.
        return await self._call("bash", payload, timeout=timeout_ms / 1000 + 30)
