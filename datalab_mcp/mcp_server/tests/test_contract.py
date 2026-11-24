"""Контракт: схема @mcp.tool совпадает с сигнатурой обработчика.

Параметры объявлены дважды (MCP-тул и обработчик). Этот тест ловит расхождение,
которое иначе всплывёт только при вызове из агента.
"""
from __future__ import annotations

import asyncio
import inspect

from mcp.server import MCPServer

from conftest import FakeClient
from src.handlers import Handlers
from src.tools import register_tools


def _schemas(handlers: Handlers) -> dict[str, dict]:
    server = MCPServer(name="datalab-test")
    register_tools(server, handlers)
    return {tool.name: tool.input_schema for tool in asyncio.run(server.list_tools())}


def test_tool_parameters_match_handlers():
    handlers = Handlers(FakeClient())
    schemas = _schemas(handlers)

    for name, schema in schemas.items():
        method = getattr(handlers, name)
        params = {
            param.name: param
            for param in inspect.signature(method).parameters.values()
            if param.name != "self"
        }
        properties = schema.get("properties", {})

        assert set(properties) == set(params), f"{name}: набор параметров разошёлся"

        required = {
            param_name
            for param_name, param in params.items()
            if param.default is inspect.Parameter.empty
        }
        assert set(schema.get("required", [])) == required, f"{name}: required разошёлся"

        for param_name, param in params.items():
            if param.default is not inspect.Parameter.empty:
                assert properties[param_name].get("default") == param.default, (
                    f"{name}.{param_name}: default разошёлся"
                )
