"""
Сервер приёма файлов для datalab.

Запуск:
    UPLOAD_DIR=/path/to/uploads JUPYTERHUB_API_TOKEN=... python server.py

Протокол (последовательный, resume по смещению):
    POST /upload/begin  {"path", "size"}          -> {"offset", "chunk_limit"}
    POST /upload/chunk  X-Path, X-Offset, тело     -> {"size"}
    POST /upload/end    {"path", "size"}           -> {"status", "path", "size"}

Целостность проверяется по размеру (как в DataCaster): sha256 не используется.
Путь в X-Path передаётся percent-encoded (заголовки HTTP только ASCII).
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import anyio
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/home/datalab/nfs/other/gigacode_test/data"))
TOKEN = os.environ.get("JUPYTERHUB_API_TOKEN")
CHUNK_LIMIT = int(os.environ.get("CHUNK_LIMIT", 32 * 1024 * 1024))

app = FastAPI()

# Один lock на путь: два клиента на один файл не портят друг другу .part.
_locks: dict = {}


def lock_for(dest: Path) -> asyncio.Lock:
    key = str(dest)
    lock = _locks.get(key)
    if lock is None:
        lock = _locks.setdefault(key, asyncio.Lock())
    return lock


def check_auth(authorization: str = Header(default="")):
    if TOKEN and authorization != f"token {TOKEN}":
        raise HTTPException(status_code=401, detail="bad token")


def safe_rel_path(rel: str) -> Path:
    """Путь внутри UPLOAD_DIR; выход наружу запрещён."""
    if not rel or "\x00" in rel:
        raise HTTPException(status_code=400, detail="bad path")
    root = UPLOAD_DIR.resolve()
    dest = (root / rel).resolve()
    try:
        dest.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad path")
    if dest == root:
        raise HTTPException(status_code=400, detail="bad path")
    return dest


def part_path(dest: Path) -> Path:
    # именно конкатенация: with_suffix() съедает ".gz"/".tar" и путает файлы
    return Path(str(dest) + ".part")


def meta_path(dest: Path) -> Path:
    return Path(str(dest) + ".part.json")


# --- синхронные операции, выполняются в thread pool ---

def _prepare_part(part: Path, expected: int) -> int:
    part.parent.mkdir(parents=True, exist_ok=True)
    if not part.exists():
        part.touch()
    cur = part.stat().st_size
    if cur > expected:
        # остаток прошлой (возможно, чужой) загрузки — начинаем заново
        with open(part, "r+b") as f:
            f.truncate(0)
        cur = 0
    return cur


def _write_meta(path: Path, expected: int) -> None:
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps({"size": expected}), encoding="utf-8")
    os.replace(tmp, path)


def _read_meta(path: Path) -> Optional[int]:
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["size"])
    except Exception:
        return None


def _finalize(part: Path, dest: Path) -> None:
    with open(part, "rb+") as f:
        f.flush()
        os.fsync(f.fileno())
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(part, dest)


@app.get("/")
def root():
    return {"status": "ok", "message": "upload server ready"}


class BeginBody(BaseModel):
    path: str
    size: int = Field(default=0, ge=0)


@app.post("/upload/begin")
async def upload_begin(body: BeginBody, authorization: str = Header(default="")):
    check_auth(authorization)
    dest = safe_rel_path(body.path)
    part = part_path(dest)
    async with lock_for(dest):
        offset = await anyio.to_thread.run_sync(_prepare_part, part, body.size)
        await anyio.to_thread.run_sync(_write_meta, meta_path(dest), body.size)
    return {"offset": offset, "chunk_limit": CHUNK_LIMIT}


@app.post("/upload/chunk")
async def upload_chunk(request: Request, authorization: str = Header(default="")):
    check_auth(authorization)
    rel = unquote(request.headers.get("X-Path", ""))
    try:
        offset = int(request.headers.get("X-Offset", "0"))
    except ValueError:
        raise HTTPException(status_code=400, detail="bad offset")
    if offset < 0:
        raise HTTPException(status_code=400, detail="bad offset")

    dest = safe_rel_path(rel)
    part = part_path(dest)

    async with lock_for(dest):
        if not part.exists():
            raise HTTPException(status_code=409, detail="call /upload/begin first")
        cur = part.stat().st_size
        if offset != cur:
            # Клиент отстал или обогнал: отдаём фактическую позицию и ничего не удаляем.
            return JSONResponse({"error": "offset mismatch", "size": cur}, status_code=409)

        expected = await anyio.to_thread.run_sync(_read_meta, meta_path(dest))
        received = 0
        f = None
        try:
            f = await anyio.to_thread.run_sync(lambda: open(part, "ab", buffering=0))
            async for block in request.stream():
                received += len(block)
                if received > CHUNK_LIMIT:
                    raise HTTPException(status_code=413, detail="chunk too large")
                if expected is not None and offset + received > expected:
                    raise HTTPException(status_code=413, detail="chunk exceeds declared size")
                await anyio.to_thread.run_sync(f.write, block)
        except BaseException:
            # Недописанный чанк откатываем: файл снова ровно offset байт.
            if f is not None:
                try:
                    await anyio.to_thread.run_sync(f.truncate, offset)
                finally:
                    await anyio.to_thread.run_sync(f.close)
            raise
        else:
            await anyio.to_thread.run_sync(f.close)

        return {"size": part.stat().st_size}


class EndBody(BaseModel):
    path: str
    size: Optional[int] = None


@app.post("/upload/end")
async def upload_end(body: EndBody, authorization: str = Header(default="")):
    check_auth(authorization)
    dest = safe_rel_path(body.path)
    part = part_path(dest)

    async with lock_for(dest):
        expected = body.size
        if expected is None:
            expected = await anyio.to_thread.run_sync(_read_meta, meta_path(dest))
        if expected is None:
            raise HTTPException(status_code=400, detail="size is unknown")

        if not part.exists():
            # параллельный клиент уже завершил этот файл — это не ошибка
            if dest.exists() and dest.stat().st_size == expected:
                return {"status": "ok", "path": str(dest), "size": expected, "already": True}
            raise HTTPException(status_code=404, detail="no part file, call /upload/begin first")

        actual = part.stat().st_size
        if actual != expected:
            return JSONResponse(
                {"error": f"size mismatch: have {actual}, expected {expected}", "size": actual},
                status_code=409,
            )
        await anyio.to_thread.run_sync(_finalize, part, dest)
        await anyio.to_thread.run_sync(meta_path(dest).unlink, True)  # missing_ok

    return {"status": "ok", "path": str(dest), "size": expected}


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PORT", 9999))
    uvicorn.run(app, host="0.0.0.0", port=port)
