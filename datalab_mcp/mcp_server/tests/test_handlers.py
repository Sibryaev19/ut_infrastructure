"""Handlers: правильные payload-ы и клиентский таймаут для bash."""
from __future__ import annotations

import asyncio

from conftest import FakeClient
from src.handlers import Handlers


def run(coro):
    return asyncio.run(coro)


def test_read_file_payload():
    client = FakeClient(text="path=/a")
    handlers = Handlers(client)
    text = run(handlers.read_file(path="/a", offset=3, limit=10))
    assert text == "path=/a"
    assert client.calls[0] == (
        "read_file",
        {"path": "/a", "offset": 3, "limit": 10},
        None,
    )


def test_workspace_info_payload():
    client = FakeClient()
    run(Handlers(client).workspace_info())
    assert client.calls[0][0] == "workspace_info"
    assert client.calls[0][1] == {}


def test_write_file_passes_optional_mtime():
    client = FakeClient()
    run(Handlers(client).write_file(path="/a", content="x", expected_mtime_ms=42))
    assert client.calls[0][1]["expected_mtime_ms"] == 42


def test_edit_file_defaults():
    client = FakeClient()
    run(Handlers(client).edit_file(path="/a", old_string="x", new_string="y"))
    payload = client.calls[0][1]
    assert payload["replace_all"] is False
    assert payload["expected_mtime_ms"] is None


def test_grep_defaults():
    client = FakeClient()
    run(Handlers(client).grep(pattern="x", path="/a"))
    payload = client.calls[0][1]
    assert payload == {"pattern": "x", "path": "/a", "include": None, "literal": False, "limit": 100}


def test_bash_waits_longer_than_server():
    client = FakeClient()
    run(Handlers(client).bash(command="sleep 1", workdir="/a", timeout_ms=5000))
    _, payload, timeout = client.calls[0]
    assert payload["timeout_ms"] == 5000
    assert timeout == 5.0 + 30


def test_bash_default_timeout():
    client = FakeClient()
    run(Handlers(client).bash(command="pwd", workdir="/a"))
    _, payload, timeout = client.calls[0]
    assert payload["timeout_ms"] == 120_000
    assert timeout == 120.0 + 30


def test_bash_omits_empty_description():
    client = FakeClient()
    run(Handlers(client).bash(command="pwd", workdir="/a", description=""))
    assert "description" not in client.calls[0][1]
