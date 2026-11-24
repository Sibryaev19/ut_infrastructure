"""workspace_info: карта местности для агента."""
from __future__ import annotations

import platform
import socket
from typing import Any

from core import limits
from core.config import Config


def workspace_info(config: Config) -> dict[str, Any]:
    workspaces = [{"name": w.name, "path": str(w.path)} for w in config.workspaces]
    payload = {
        "host": socket.gethostname(),
        "os": platform.system(),
        "workspaces": workspaces,
        "limits": {
            "read_file": {
                "default_lines": limits.READ_DEFAULT_LINES,
                "max_lines": limits.READ_MAX_LINES,
                "max_bytes_per_response": limits.READ_MAX_BYTES,
                "max_line_chars": limits.MAX_LINE_CHARS,
            },
            "write_file": {"max_bytes": limits.WRITE_MAX_BYTES},
            "edit_file": {"max_file_bytes": limits.EDIT_MAX_BYTES},
            "list_dir": {"max_entries": limits.LIST_MAX_ENTRIES},
            "glob": {"max_results": limits.SEARCH_MAX_RESULTS},
            "grep": {
                "max_results": limits.SEARCH_MAX_RESULTS,
                "max_line_chars": limits.SEARCH_MAX_LINE_CHARS,
                "max_scanned_files": limits.SEARCH_MAX_FILES,
            },
            "bash": {
                "default_timeout_ms": limits.BASH_DEFAULT_TIMEOUT_MS,
                "max_timeout_ms": limits.BASH_MAX_TIMEOUT_MS,
                "max_inline_chars": limits.BASH_MAX_INLINE_CHARS,
            },
        },
        "path_rules": (
            "paths must be POSIX absolute; reads are unrestricted; "
            "writes are allowed only inside workspaces"
        ),
    }

    lines = [
        f"host={payload['host']} os={payload['os']}",
        "workspaces:",
    ]
    for item in workspaces:
        lines.append(f"  {item['name']} = {item['path']}")
    lines.append(f"path_rules={payload['path_rules']}")
    lines.append(
        "limits: "
        f"read={limits.READ_DEFAULT_LINES} lines / {limits.READ_MAX_BYTES} bytes; "
        f"write={limits.WRITE_MAX_BYTES} bytes; "
        f"edit={limits.EDIT_MAX_BYTES} bytes; "
        f"list={limits.LIST_MAX_ENTRIES}; "
        f"glob/grep={limits.SEARCH_MAX_RESULTS}; "
        f"bash={limits.BASH_MAX_INLINE_CHARS} chars, "
        f"timeout {limits.BASH_DEFAULT_TIMEOUT_MS}..{limits.BASH_MAX_TIMEOUT_MS} ms"
    )
    return {"text": "\n".join(lines), "meta": payload}
