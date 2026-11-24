"""MCP-уровень: набор тулов, текст результата, isError для ошибок datalab."""
from __future__ import annotations

import asyncio

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from conftest import FakeClient
from src.datalab import DatalabError, DatalabTransportError
from src.handlers import Handlers
from src.tools import register_tools

EXPECTED_TOOLS = {
    "workspace_info",
    "list_dir",
    "read_file",
    "write_file",
    "edit_file",
    "glob",
    "grep",
    "bash",
}


def run(coro):
    return asyncio.run(coro)


def make_server(client: FakeClient) -> MCPServer:
    server = MCPServer(name="datalab-test")
    register_tools(server, Handlers(client))
    return server


def test_exposes_exactly_eight_tools():
    tools = run(make_server(FakeClient()).list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_success_result_carries_server_text():
    server = make_server(FakeClient(text="path=/a\n\n     1\tx"))
    result = run(server.call_tool("read_file", {"path": "/a"}))
    assert result.is_error is False
    assert result.content[0].text == "path=/a\n\n     1\tx"


def test_datalab_error_is_reported_as_iserror():
    error = DatalabError(
        "outside_workspace",
        "write outside workspaces is not allowed: /tmp/x",
        "Доступные области: ws=/home/datalab/ws",
        status=403,
    )
    server = make_server(FakeClient(error=error))

    with pytest.raises(ToolError) as info:
        run(server.call_tool("write_file", {"path": "/tmp/x", "content": "y"}))

    message = str(info.value)
    assert "outside_workspace" in message
    assert "Доступные области" in message


def test_transport_error_is_reported_as_iserror():
    error = DatalabTransportError(
        "connection",
        "cannot reach datalab at https://x/tools/read_file",
        "Проверьте DATALAB_URL",
    )
    server = make_server(FakeClient(error=error))

    with pytest.raises(ToolError) as info:
        run(server.call_tool("read_file", {"path": "/a"}))

    assert "cannot reach datalab" in str(info.value)


def test_bash_tool_accepts_description():
    client = FakeClient(text="exit_code=0")
    server = make_server(client)
    result = run(
        server.call_tool(
            "bash",
            {"command": "pwd", "workdir": "/a", "description": "show cwd"},
        )
    )
    assert result.is_error is False
    assert client.calls[0][1]["description"] == "show cwd"
