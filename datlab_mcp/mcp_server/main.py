"""Инициализация MCP-сервера и запуск по stdio.

Агент поднимает этот процесс сам по конфигу (command + args + env),
пользователю не нужно запускать или убивать сервер вручную.

stdout занят протоколом: логирование только в stderr.
"""
from __future__ import annotations

import logging
import sys

from mcp.server import MCPServer

from src.config import ConfigError, Settings, load_settings
from src.datalab import DatalabClient
from src.handlers import Handlers
from src.tools import register_tools

INSTRUCTIONS = """\
You are connected to a remote Linux machine (datalab), not to the local computer.
All file paths are absolute POSIX paths on that machine, e.g. /home/datalab/project/app.py.
Paths of the user's local machine do not exist there.

Start with workspace_info: it returns the project areas (the only roots where
write_file and edit_file are allowed) and the per-tool limits.
read_file, list_dir, glob and grep may read anywhere on the remote machine.
Files are referenced as /absolute/path:line — these are remote paths.

bash runs a fresh shell per call; pass workdir explicitly, do not rely on cd.
"""


def build_server(settings: Settings, client: DatalabClient | None = None) -> MCPServer:
    server = MCPServer(
        name="datalab",
        instructions=INSTRUCTIONS,
        log_level="INFO",
    )
    register_tools(server, Handlers(client or DatalabClient(settings)))
    return server


def main() -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx логирует каждый запрос на INFO — для stdio-сервера это лишний шум
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        settings = load_settings()
    except ConfigError as exc:
        logging.error("configuration error: %s", exc)
        return 1

    logging.info("datalab MCP server -> %s", settings.datalab_url)
    build_server(settings).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
