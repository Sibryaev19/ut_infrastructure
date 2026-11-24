"""DatalabClient: URL, заголовок токена, разбор ответов и ошибок."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from conftest import make_http_client, make_settings
from src.datalab import DatalabClient, DatalabError, DatalabTransportError


def run(coro):
    return asyncio.run(coro)


def test_posts_to_tool_endpoint_with_token():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True, "text": "path=/a", "meta": {"m": 1}})

    async def scenario():
        async with make_http_client(handler) as raw:
            client = DatalabClient(make_settings(), client=raw)
            return await client.call("read_file", {"path": "/a"})

    response = run(scenario())
    assert response.text == "path=/a"
    assert response.meta == {"m": 1}
    assert seen["url"] == "https://datalab.test/9999/tools/read_file"
    assert seen["auth"] == "token secret-token"
    assert '"path"' in seen["body"]


def test_server_error_becomes_datalab_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": "outside_workspace",
                    "message": "write outside workspaces is not allowed: /tmp/x",
                    "hint": "Доступные области: ws=/home/datalab/ws",
                }
            },
        )

    async def scenario():
        async with make_http_client(handler) as raw:
            client = DatalabClient(make_settings(), client=raw)
            await client.call("write_file", {"path": "/tmp/x", "content": "y"})

    with pytest.raises(DatalabError) as info:
        run(scenario())

    error = info.value
    assert error.code == "outside_workspace"
    assert error.status == 403
    assert error.hint.startswith("Доступные области")
    text = str(error)
    assert "error=outside_workspace" in text
    assert "message=write outside workspaces" in text
    assert "hint=" in text


def test_fastapi_detail_is_used_as_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "invalid request body"})

    async def scenario():
        async with make_http_client(handler) as raw:
            client = DatalabClient(make_settings(), client=raw)
            await client.call("bash", {})

    with pytest.raises(DatalabError) as info:
        run(scenario())
    assert info.value.code == "http_error"
    assert "invalid request body" in info.value.message


def test_non_json_error_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    async def scenario():
        async with make_http_client(handler) as raw:
            client = DatalabClient(make_settings(), client=raw)
            await client.call("read_file", {"path": "/a"})

    with pytest.raises(DatalabError) as info:
        run(scenario())
    assert info.value.code == "http_error"
    assert "bad gateway" in info.value.hint


def test_unexpected_success_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    async def scenario():
        async with make_http_client(handler) as raw:
            client = DatalabClient(make_settings(), client=raw)
            await client.call("read_file", {"path": "/a"})

    with pytest.raises(DatalabError) as info:
        run(scenario())
    assert info.value.code == "bad_response"


def test_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async def scenario():
        async with make_http_client(handler) as raw:
            client = DatalabClient(make_settings(), client=raw)
            await client.call("read_file", {"path": "/a"})

    with pytest.raises(DatalabTransportError) as info:
        run(scenario())
    assert info.value.kind == "connection"
    assert "cannot reach datalab" in str(info.value)


def test_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    async def scenario():
        async with make_http_client(handler) as raw:
            client = DatalabClient(make_settings(), client=raw)
            await client.call("bash", {"command": "sleep 1"}, timeout=31)

    with pytest.raises(DatalabTransportError) as info:
        run(scenario())
    assert info.value.kind == "timeout"
    assert "within 31s" in str(info.value)


def test_health():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/health")
        return httpx.Response(200, json={"ok": True})

    async def scenario():
        async with make_http_client(handler) as raw:
            client = DatalabClient(make_settings(), client=raw)
            return await client.health()

    assert run(scenario()) is True
