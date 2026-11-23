"""
Локальный клиент загрузки файлов в datalab.
Запуск: python client.py  ->  веб-интерфейс на http://localhost:8090
Настройки — в .env (см. .env.example)
"""
import os
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

load_dotenv()

DATALAB_URL = os.environ["DATALAB_URL"].rstrip("/")
DATALAB_TOKEN = os.environ["DATALAB_TOKEN"]
CLIENT_PORT = int(os.environ.get("CLIENT_PORT", 8090))
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 4 * 1024 * 1024))  # 4 МБ
MAX_BODY = int(os.environ.get("MAX_BODY", 64 * 1024 * 1024))
TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", 120))
VERIFY_TLS = os.environ.get("VERIFY_TLS", "false").lower() not in ("0", "false", "no")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI()


def auth_headers() -> dict:
    return {"Authorization": f"token {DATALAB_TOKEN}"}


def datalab_error(r: httpx.Response) -> JSONResponse:
    """Прокидываем ошибку datalab как есть — браузеру нужен `size` для ресинка."""
    try:
        data = r.json()
    except Exception:
        return JSONResponse({"error": r.text[:300]}, status_code=r.status_code)
    if isinstance(data, dict) and "detail" in data:
        detail = data["detail"]
        out = detail if isinstance(detail, dict) else {"error": str(detail)}
        return JSONResponse(out, status_code=r.status_code)
    if isinstance(data, dict):
        return JSONResponse(data, status_code=r.status_code)
    return JSONResponse({"error": str(data)}, status_code=r.status_code)


async def datalab_json(endpoint: str, payload: dict):
    async with httpx.AsyncClient(timeout=TIMEOUT, verify=VERIFY_TLS) as cli:
        r = await cli.post(f"{DATALAB_URL}{endpoint}", headers=auth_headers(), json=payload)
    if r.status_code >= 400:
        return datalab_error(r)
    return r.json()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/config")
def config():
    return {"chunk_size": CHUNK_SIZE}


class BeginBody(BaseModel):
    path: str
    size: int = 0


@app.post("/api/begin")
async def api_begin(body: BeginBody):
    return await datalab_json("/upload/begin", {"path": body.path, "size": body.size})


@app.post("/api/chunk")
async def api_chunk(request: Request):
    # Путь остаётся percent-encoded: HTTP-заголовки допускают только ASCII.
    rel = request.headers.get("X-Path", "")
    offset = request.headers.get("X-Offset", "0")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(status_code=413, detail="chunk too large")
    headers = {
        **auth_headers(),
        "Content-Type": "application/octet-stream",
        "X-Path": rel,
        "X-Offset": offset,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT, verify=VERIFY_TLS) as cli:
        # bytes, а не генератор: httpx сам выставит Content-Length
        r = await cli.post(f"{DATALAB_URL}/upload/chunk", headers=headers, content=body)
    if r.status_code >= 400:
        return datalab_error(r)
    return r.json()


class EndBody(BaseModel):
    path: str
    size: Optional[int] = None


@app.post("/api/end")
async def api_end(body: EndBody):
    return await datalab_json("/upload/end", {"path": body.path, "size": body.size})


@app.exception_handler(HTTPException)
async def http_exc_handler(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=CLIENT_PORT)
