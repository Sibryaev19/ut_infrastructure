"""Объявления MCP-тулов: схемы, описания и перевод ошибок в isError.

Сама логика — в src/handlers. Здесь только контракт для агента.
"""
from __future__ import annotations

from typing import Annotated, Any, Awaitable, Callable

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from ..datalab import DatalabError, DatalabTransportError
from ..handlers import Handlers

PathArg = Annotated[
    str,
    Field(description="Absolute POSIX path on datalab, e.g. /home/datalab/project/app.py"),
]
MtimeArg = Annotated[
    int | None,
    Field(
        description="mtime_ms from a previous read; if the file changed on disk, "
        "the call fails with stale_file instead of overwriting"
    ),
]


def register_tools(mcp: MCPServer, handlers: Handlers) -> None:
    async def invoke(method: Callable[..., Awaitable[str]], **kwargs: Any) -> str:
        """Ошибки datalab отдаём агенту как результат инструмента с isError."""
        try:
            return await method(**kwargs)
        except (DatalabError, DatalabTransportError) as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        name="workspace_info",
        description=(
            "Show datalab project areas (the only roots where writes are allowed), "
            "the remote host, and per-tool limits. Call this first: all paths are "
            "POSIX absolute paths on the remote machine, not on yours."
        ),
        structured_output=False,
    )
    async def workspace_info() -> str:
        return await invoke(handlers.workspace_info)

    @mcp.tool(
        name="list_dir",
        description=(
            "List one directory on datalab (non-recursive). Returns type, size, "
            "mtime and symlink targets. Use glob for recursive search."
        ),
        structured_output=False,
    )
    async def list_dir(path: PathArg, depth: int = 1) -> str:
        return await invoke(handlers.list_dir, path=path, depth=depth)

    @mcp.tool(
        name="read_file",
        description=(
            "Read a text file on datalab. Lines are numbered like 'cat -n' "
            "(strip the prefix before building old_string for edit_file). "
            "Use offset/limit for large files; binary files are rejected."
        ),
        structured_output=False,
    )
    async def read_file(path: PathArg, offset: int = 1, limit: int = 2000) -> str:
        return await invoke(handlers.read_file, path=path, offset=offset, limit=limit)

    @mcp.tool(
        name="write_file",
        description=(
            "Create or overwrite a text file on datalab. Atomic write; parents are "
            "created; the file mode is preserved. Writes are allowed only inside "
            "project areas. Pass expected_mtime_ms to avoid clobbering a file that "
            "changed since you read it."
        ),
        structured_output=False,
    )
    async def write_file(path: PathArg, content: str, expected_mtime_ms: MtimeArg = None) -> str:
        return await invoke(
            handlers.write_file,
            path=path,
            content=content,
            expected_mtime_ms=expected_mtime_ms,
        )

    @mcp.tool(
        name="edit_file",
        description=(
            "Replace an exact string in a file on datalab. old_string must occur "
            "exactly once unless replace_all=true. Matching is literal: whitespace "
            "and line endings must match (the error hint mentions CRLF files)."
        ),
        structured_output=False,
    )
    async def edit_file(
        path: PathArg,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        expected_mtime_ms: MtimeArg = None,
    ) -> str:
        return await invoke(
            handlers.edit_file,
            path=path,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
            expected_mtime_ms=expected_mtime_ms,
        )

    @mcp.tool(
        name="glob",
        description=(
            "Find files by glob pattern on datalab (supports **). Skips .git, "
            "__pycache__, .venv, node_modules and hidden directories. Results are "
            "sorted by mtime, newest first; a truncated list is spilled to a file."
        ),
        structured_output=False,
    )
    async def glob(pattern: str, path: PathArg, limit: int = 100) -> str:
        return await invoke(handlers.glob, pattern=pattern, path=path, limit=limit)

    @mcp.tool(
        name="grep",
        description=(
            "Search file contents on datalab with a regular expression, or with "
            "literal=true for a plain substring. Output is 'relative/path:line:text'. "
            "Skips binary files and heavy directories."
        ),
        structured_output=False,
    )
    async def grep(
        pattern: str,
        path: PathArg,
        include: Annotated[
            str | None, Field(description="Filter files by name glob, e.g. *.py")
        ] = None,
        literal: bool = False,
        limit: int = 100,
    ) -> str:
        return await invoke(
            handlers.grep,
            pattern=pattern,
            path=path,
            include=include,
            literal=literal,
            limit=limit,
        )

    @mcp.tool(
        name="bash",
        description=(
            "Run a shell command on datalab (fresh bash -lc per call). Working "
            "directory does not persist: pass workdir instead of relying on cd. "
            "Non-interactive: use -y / --no-pager. On timeout the process group is "
            "killed and partial output is returned with timed_out=true."
        ),
        structured_output=False,
    )
    async def bash(
        command: str,
        workdir: Annotated[str, Field(description="Absolute path of the working directory")],
        timeout_ms: int = 120_000,
        description: Annotated[
            str | None, Field(description="Short note about what the command does")
        ] = None,
    ) -> str:
        return await invoke(
            handlers.bash,
            command=command,
            workdir=workdir,
            timeout_ms=timeout_ms,
            description=description,
        )
