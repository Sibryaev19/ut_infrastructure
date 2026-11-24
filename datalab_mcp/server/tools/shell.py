"""bash: запуск команд на datalab.

Свежая оболочка на каждый вызов (без персистентного `cd`), таймаут с убийством
группы процессов, вывод сверх лимита уезжает в spill-файл.
"""
from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path
from typing import Any

from core import limits, paths
from core.config import Config
from core.errors import ToolError
from core.spill import new_spill_path


class _Capture:
    """Копит вывод в памяти до порога, дальше пишет всё в spill-файл."""

    def __init__(self, spill_path: Path, memory_limit: int) -> None:
        self._spill_path = spill_path
        self._memory_limit = memory_limit
        self._buffer = bytearray()
        self._file = None
        self.total = 0

    def write(self, chunk: bytes) -> None:
        self.total += len(chunk)
        if self._file is not None:
            self._file.write(chunk)
            return
        self._buffer.extend(chunk)
        if len(self._buffer) > self._memory_limit:
            self._file = open(self._spill_path, "wb")
            self._file.write(self._buffer)

    def _read_tail(self, max_chars: int) -> str:
        # 4 байта на символ — запас на UTF-8, чтобы не разрезать символ
        with open(self._spill_path, "rb") as handle:
            handle.seek(max(0, self.total - max_chars * 4))
            data = handle.read()
        text = data.decode("utf-8", "replace")
        return text[-max_chars:]

    def finalize(self, inline_limit: int) -> tuple[str | None, str, int]:
        """Возвращает (spill-путь, текст для агента, всего байт)."""
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None
            return str(self._spill_path), self._read_tail(inline_limit), self.total

        text = bytes(self._buffer).decode("utf-8", "replace")
        if self.total > inline_limit:
            self._spill_path.parent.mkdir(parents=True, exist_ok=True)
            self._spill_path.write_bytes(bytes(self._buffer))
            return str(self._spill_path), text[-inline_limit:], self.total
        return None, text, self.total


async def _pump(stream: asyncio.StreamReader, capture: _Capture) -> None:
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        capture.write(chunk)


def _kill_group(pid: int) -> None:
    """Убиваем всю группу: иначе дети (npm, pytest, ssh) переживут таймаут."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


async def run_bash(
    config: Config,
    command: str,
    workdir: str,
    timeout_ms: int = limits.BASH_DEFAULT_TIMEOUT_MS,
    description: str | None = None,
) -> dict[str, Any]:
    if not command or not command.strip():
        raise ToolError("bad_request", "command is required")
    if not workdir or not workdir.strip():
        raise ToolError(
            "bad_path",
            "workdir is required",
            "Передайте абсолютный путь каталога, например /home/datalab/project.",
        )

    directory = paths.require_dir(paths.resolve_read(workdir), "workdir")

    timeout_ms = int(timeout_ms)
    if timeout_ms < limits.BASH_MIN_TIMEOUT_MS:
        timeout_ms = limits.BASH_MIN_TIMEOUT_MS
    if timeout_ms > limits.BASH_MAX_TIMEOUT_MS:
        timeout_ms = limits.BASH_MAX_TIMEOUT_MS

    env = os.environ.copy()
    env.update(
        {
            "PAGER": "cat",
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "TERM": "dumb",
        }
    )

    stdout_spill = new_spill_path(config, "bash-stdout")
    stderr_spill = new_spill_path(config, "bash-stderr")
    out_capture = _Capture(stdout_spill, limits.BASH_CAPTURE_MAX_BYTES)
    err_capture = _Capture(stderr_spill, limits.BASH_CAPTURE_MAX_BYTES)

    started = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            cwd=str(directory),
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise ToolError(
            "internal", "bash not found on the server", "Сервер должен быть Linux."
        ) from exc

    readers = [
        asyncio.create_task(_pump(process.stdout, out_capture)),
        asyncio.create_task(_pump(process.stderr, err_capture)),
    ]

    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_ms / 1000)
    except asyncio.TimeoutError:
        timed_out = True
        _kill_group(process.pid)
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass

    await asyncio.gather(*readers, return_exceptions=True)
    duration_ms = int((time.monotonic() - started) * 1000)

    stdout_path, stdout_text, stdout_total = out_capture.finalize(
        limits.BASH_MAX_INLINE_CHARS
    )
    stderr_path, stderr_text, stderr_total = err_capture.finalize(
        limits.BASH_MAX_INLINE_CHARS
    )

    exit_code = process.returncode
    header = (
        f"workdir={directory}\n"
        f"exit_code={exit_code} timed_out={'true' if timed_out else 'false'} "
        f"duration_ms={duration_ms}"
    )
    if description:
        header += f"\ndescription={description}"

    parts = [header, f"--- stdout ({stdout_total} bytes) ---", stdout_text or ""]
    if stderr_text:
        parts.append(f"--- stderr ({stderr_total} bytes) ---")
        parts.append(stderr_text)
    for label, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        if path:
            parts.append(f"[{label} truncated; full log: {path}]")

    return {
        "text": "\n".join(parts),
        "meta": {
            "workdir": str(directory),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "stdout_bytes": stdout_total,
            "stderr_bytes": stderr_total,
            "stdout_spill": stdout_path,
            "stderr_spill": stderr_path,
            "truncated": bool(stdout_path or stderr_path),
        },
    }
