"""FastAPI-сервер на datalab: файловые и shell-инструменты для агента.

Запуск на datalab:
    WORKSPACES="project=/home/datalab/nfs/other/project" \
    PORT=9999 python app.py

Или через uvicorn:
    WORKSPACES=... uvicorn app:build_default_app --factory --host 0.0.0.0 --port 9999

Авторизация — на стороне платформы (jupyterhub): сервер токен не проверяет.
"""
from __future__ import annotations

import logging
import os
import time
from functools import partial
from typing import Any, Callable

import anyio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import limits
from core.config import Config, load_config
from core.errors import ToolError
from tools import fs, info, search, shell

logger = logging.getLogger("datalab.server")


# --- схемы запросов ---

class ListDirArgs(BaseModel):
    path: str


class ReadFileArgs(BaseModel):
    path: str
    offset: int = 1
    limit: int = limits.READ_DEFAULT_LINES


class WriteFileArgs(BaseModel):
    path: str
    content: str
    expected_mtime_ms: int | None = None


class EditFileArgs(BaseModel):
    path: str
    old_string: str
    new_string: str
    replace_all: bool = False
    expected_mtime_ms: int | None = None


class GlobArgs(BaseModel):
    pattern: str
    path: str
    limit: int = limits.SEARCH_MAX_RESULTS


class GrepArgs(BaseModel):
    pattern: str
    path: str
    include: str | None = None
    literal: bool = False
    limit: int = limits.SEARCH_MAX_RESULTS


class BashArgs(BaseModel):
    command: str
    workdir: str
    timeout_ms: int = limits.BASH_DEFAULT_TIMEOUT_MS
    description: str | None = None


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="datalab agent server", version="0.1.0")
    app.state.config = config

    # --- обработчики ошибок ---

    @app.exception_handler(ToolError)
    async def _tool_error_handler(request: Request, exc: ToolError) -> JSONResponse:
        logger.warning("tool error %s: %s", exc.code, exc.message)
        return JSONResponse(exc.to_body(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "bad_request",
                    "message": "invalid request body",
                    "hint": str(exc.errors()[:3]),
                }
            },
            status_code=400,
        )

    @app.exception_handler(Exception)
    async def _internal_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return JSONResponse(
            {"error": {"code": "internal", "message": "internal server error"}},
            status_code=500,
        )

    # --- помощники ---

    def ok(result: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "text": result["text"], "meta": result["meta"]}

    async def call(
        tool: str, func: Callable[..., dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            result = await anyio.to_thread.run_sync(partial(func, config, **kwargs))
        finally:
            logger.info("%s %.1f ms", tool, (time.monotonic() - started) * 1000)
        return ok(result)

    # --- служебные эндпоинты ---

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "workspaces": len(config.workspaces)}

    @app.get("/info")
    async def get_info() -> dict[str, Any]:
        return ok(info.workspace_info(config))

    @app.post("/tools/workspace_info")
    async def tool_workspace_info() -> dict[str, Any]:
        return ok(info.workspace_info(config))

    # --- файловые инструменты ---

    @app.post("/tools/list_dir")
    async def tool_list_dir(args: ListDirArgs) -> dict[str, Any]:
        return await call("list_dir", fs.list_dir, path=args.path)

    @app.post("/tools/read_file")
    async def tool_read_file(args: ReadFileArgs) -> dict[str, Any]:
        return await call(
            "read_file", fs.read_file, path=args.path, offset=args.offset, limit=args.limit
        )

    @app.post("/tools/write_file")
    async def tool_write_file(args: WriteFileArgs) -> dict[str, Any]:
        return await call(
            "write_file",
            fs.write_file,
            path=args.path,
            content=args.content,
            expected_mtime_ms=args.expected_mtime_ms,
        )

    @app.post("/tools/edit_file")
    async def tool_edit_file(args: EditFileArgs) -> dict[str, Any]:
        return await call(
            "edit_file",
            fs.edit_file,
            path=args.path,
            old_string=args.old_string,
            new_string=args.new_string,
            replace_all=args.replace_all,
            expected_mtime_ms=args.expected_mtime_ms,
        )

    # --- поиск ---

    @app.post("/tools/glob")
    async def tool_glob(args: GlobArgs) -> dict[str, Any]:
        return await call(
            "glob", search.glob_search, pattern=args.pattern, path=args.path, limit=args.limit
        )

    @app.post("/tools/grep")
    async def tool_grep(args: GrepArgs) -> dict[str, Any]:
        return await call(
            "grep",
            search.grep_search,
            pattern=args.pattern,
            path=args.path,
            include=args.include,
            literal=args.literal,
            limit=args.limit,
        )

    # --- терминал ---

    @app.post("/tools/bash")
    async def tool_bash(args: BashArgs) -> dict[str, Any]:
        started = time.monotonic()
        try:
            result = await shell.run_bash(
                config,
                command=args.command,
                workdir=args.workdir,
                timeout_ms=args.timeout_ms,
                description=args.description,
            )
        finally:
            logger.info("bash %.1f ms", (time.monotonic() - started) * 1000)
        return ok(result)

    return app


def build_default_app() -> FastAPI:
    """Точка входа для `uvicorn app:build_default_app --factory`."""
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("workspaces: %s", config.workspace_names())
    return create_app(config)


if __name__ == "__main__":
    application = build_default_app()
    uvicorn.run(application, host="0.0.0.0", port=int(os.environ.get("PORT", "9999")))
