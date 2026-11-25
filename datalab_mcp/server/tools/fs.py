"""Файловые инструменты: read_file, write_file, edit_file, list_dir."""
from __future__ import annotations

import os
import stat as stat_module
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core import limits, paths
from core.config import Config
from core.errors import ToolError


# --- общие помощники ---

def _mtime_ms(path: Path) -> int:
    return int(round(path.stat().st_mtime * 1000))


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "K", "M", "G", "T"):
        if value < 1024 or unit == "T":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{size}B"


def _atomic_write(path: Path, data: bytes, mode: int | None) -> None:
    """Запись через временный файл в том же каталоге: читатель не увидит полуфайл."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{limits.TMP_PREFIX}{path.name}.{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # os.replace создаёт новый inode с дефолтным режимом: 755 -> 644 без этого
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _check_stale(path: Path, expected_mtime_ms: int | None, existed: bool) -> None:
    if expected_mtime_ms is None:
        return
    if not existed:
        raise ToolError(
            "stale_file",
            f"file does not exist: {path}",
            "expected_mtime_ms задаётся только для существующего файла; "
            "уберите параметр, чтобы создать файл.",
        )
    current = _mtime_ms(path)
    if current != int(expected_mtime_ms):
        raise ToolError(
            "stale_file",
            f"file changed on disk: {path}",
            f"mtime_ms сейчас {current}, ожидался {int(expected_mtime_ms)}. "
            "Прочитайте файл заново и повторите правку.",
            extra={"mtime_ms": current},
        )


def _decode_line(raw: bytes) -> tuple[str, bool, bool]:
    """Строка без завершающего перевода. Возвращает (текст, lossy, crlf)."""
    lossy = False
    crlf = False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", "replace")
        lossy = True
    if text.endswith("\r\n"):
        text = text[:-2]
        crlf = True
    elif text.endswith("\n"):
        text = text[:-1]
    return text, lossy, crlf


def _match_lines(text: str, needle: str) -> list[int]:
    lines: list[int] = []
    start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            break
        lines.append(text.count("\n", 0, index) + 1)
        start = index + len(needle)
    return lines


# --- read_file ---

def read_file(
    config: Config,
    path: str,
    offset: int = 1,
    limit: int = limits.READ_DEFAULT_LINES,
) -> dict[str, Any]:
    if offset < 1:
        raise ToolError("bad_request", "offset must be >= 1", "Нумерация строк начинается с 1.")
    if limit < 1:
        raise ToolError("bad_request", "limit must be >= 1")
    limit = min(limit, limits.READ_MAX_LINES)

    target = paths.require_file(paths.resolve_read(path))
    size = target.stat().st_size
    mtime = _mtime_ms(target)

    with open(target, "rb") as handle:
        head = handle.read(limits.BINARY_SNIFF_BYTES)
    if b"\x00" in head:
        raise ToolError(
            "binary_file",
            f"file looks binary (NUL byte): {target}",
            "Для двоичных файлов используйте bash (file, xxd, python) — "
            "read_file отдаёт только текст.",
        )

    if size == 0:
        return {
            "text": f"path={target}\nsize=0 mtime_ms={mtime}\n\nfile is empty",
            "meta": {
                "path": str(target),
                "size": 0,
                "mtime_ms": mtime,
                "total_lines": 0,
                "offset": offset,
                "returned": 0,
                "next_offset": None,
                "truncated_by_bytes": False,
                "encoding_lossy": False,
                "crlf": False,
            },
        }

    collected: list[tuple[int, str]] = []
    bytes_out = 0
    total: int | None = 0
    lossy = False
    crlf = False
    truncated_by_bytes = False
    next_offset: int | None = None
    collecting = True

    with open(target, "rb") as handle:
        for lineno, raw in enumerate(handle, 1):
            total = lineno
            if lineno < offset:
                continue
            if not collecting:
                # считаем total_lines дальше, но только для файлов разумного размера
                if size > limits.TOTAL_SCAN_BYTES:
                    total = None
                    break
                continue
            if len(collected) >= limit:
                next_offset = lineno
                collecting = False
                if size > limits.TOTAL_SCAN_BYTES:
                    total = None
                    break
                continue

            text, line_lossy, line_crlf = _decode_line(raw)
            lossy = lossy or line_lossy
            crlf = crlf or line_crlf
            if len(text) > limits.MAX_LINE_CHARS:
                cut = len(text) - limits.MAX_LINE_CHARS
                text = f"{text[: limits.MAX_LINE_CHARS]} …[truncated {cut} chars]"

            nbytes = len(text.encode("utf-8")) + 1
            if collected and bytes_out + nbytes > limits.READ_MAX_BYTES:
                truncated_by_bytes = True
                next_offset = lineno
                collecting = False
                if size > limits.TOTAL_SCAN_BYTES:
                    total = None
                    break
                continue

            collected.append((lineno, text))
            bytes_out += nbytes

    header = (
        f"path={target}\n"
        f"size={size} mtime_ms={mtime} "
        f"total_lines={total if total is not None else 'unknown'} "
        f"offset={offset} returned={len(collected)}"
    )
    if next_offset is not None:
        header += f" next_offset={next_offset}"
    if truncated_by_bytes:
        header += " truncated_by_bytes=true"
    if lossy:
        header += " encoding_lossy=true"
    if crlf:
        header += " crlf=true"

    if collected:
        body = "\n".join(f"{lineno:>6}\t{text}" for lineno, text in collected)
    else:
        body = f"(no lines at offset {offset}; total_lines={total if total is not None else 'unknown'})"

    return {
        "text": f"{header}\n\n{body}",
        "meta": {
            "path": str(target),
            "size": size,
            "mtime_ms": mtime,
            "total_lines": total,
            "offset": offset,
            "returned": len(collected),
            "next_offset": next_offset,
            "truncated_by_bytes": truncated_by_bytes,
            "encoding_lossy": lossy,
            "crlf": crlf,
        },
    }


# --- write_file ---

def write_file(
    config: Config,
    path: str,
    content: str,
    expected_mtime_ms: int | None = None,
) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ToolError("bad_request", "content must be a string")
    data = content.encode("utf-8")
    if len(data) > limits.WRITE_MAX_BYTES:
        raise ToolError(
            "too_large",
            f"content is {len(data)} bytes, limit is {limits.WRITE_MAX_BYTES}",
            "Для больших файлов используйте bash (cat > file, python) или загрузку чанками.",
        )

    target = paths.resolve_write(path, config)
    existed = target.exists()
    if existed and target.is_dir():
        raise ToolError("is_directory", f"path is a directory: {target}")
    _check_stale(target, expected_mtime_ms, existed)

    mode = stat_module.S_IMODE(target.stat().st_mode) if existed else None
    _atomic_write(target, data, mode)
    mtime = _mtime_ms(target)

    return {
        "text": (
            f"path={target}\n"
            f"wrote={len(data)} bytes mtime_ms={mtime}"
            f"{'' if existed else ' created=true'}"
        ),
        "meta": {
            "path": str(target),
            "bytes": len(data),
            "mtime_ms": mtime,
            "created": not existed,
            "mode": None if mode is None else oct(mode),
        },
    }


# --- edit_file ---

def edit_file(
    config: Config,
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    expected_mtime_ms: int | None = None,
) -> dict[str, Any]:
    if not old_string:
        raise ToolError("bad_request", "old_string must not be empty")
    if old_string == new_string:
        raise ToolError(
            "bad_request",
            "old_string and new_string are identical",
            "Правка ничего не меняет — проверьте аргументы.",
        )

    target = paths.require_file(paths.resolve_write(path, config))
    size = target.stat().st_size
    if size > limits.EDIT_MAX_BYTES:
        raise ToolError(
            "too_large",
            f"file is {size} bytes, edit limit is {limits.EDIT_MAX_BYTES}",
            "Правьте большой файл через bash (sed, python) — edit_file читает файл целиком.",
        )
    _check_stale(target, expected_mtime_ms, existed=True)

    data = target.read_bytes()
    if b"\x00" in data[: limits.BINARY_SNIFF_BYTES]:
        raise ToolError("binary_file", f"file looks binary (NUL byte): {target}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(
            "encoding_error",
            f"file is not valid UTF-8: {target}",
            f"Ошибка декодирования на байте {exc.start}. Правьте через bash (sed, python).",
        ) from exc

    count = text.count(old_string)
    if count == 0:
        hint = "old_string not found"
        if "\r\n" in text and "\r\n" not in old_string:
            hint = (
                "Файл использует CRLF-переводы строк: в old_string нужны \\r\\n, "
                "а не \\n."
            )
        raise ToolError("not_found_in_file", f"old_string not found in {target}", hint)

    if count > 1 and not replace_all:
        lines = _match_lines(text, old_string)
        raise ToolError(
            "not_unique",
            f"old_string occurs {count} times in {target}",
            f"Совпадения на строках: {lines[:10]}. Добавьте контекст в old_string "
            "или передайте replace_all=true.",
            extra={"matches": count, "lines": lines[:10]},
        )

    new_text = text.replace(old_string, new_string) if replace_all else text.replace(
        old_string, new_string, 1
    )
    replaced = count if replace_all else 1
    mode = stat_module.S_IMODE(target.stat().st_mode)
    _atomic_write(target, new_text.encode("utf-8"), mode)
    mtime = _mtime_ms(target)

    return {
        "text": (
            f"path={target}\n"
            f"replaced={replaced} mtime_ms={mtime}"
        ),
        "meta": {
            "path": str(target),
            "replaced": replaced,
            "matches": count,
            "mtime_ms": mtime,
        },
    }


# --- list_dir ---

def list_dir(config: Config, path: str) -> dict[str, Any]:
    target = paths.require_dir(paths.resolve_read(path))

    entries: list[tuple[str, str, int, float, str]] = []
    with os.scandir(target) as iterator:
        for entry in iterator:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if entry.is_symlink():
                kind = "l"
                try:
                    tail = f" -> {os.readlink(entry.path)}"
                except OSError:
                    tail = " -> ?"
            elif entry.is_dir(follow_symlinks=False):
                kind, tail = "d", ""
            else:
                kind, tail = "f", ""
            entries.append((kind, entry.name, info.st_size, info.st_mtime, tail))

    total = len(entries)
    entries.sort(key=lambda item: (0 if item[0] == "d" else 1, item[1].lower()))
    truncated = total > limits.LIST_MAX_ENTRIES
    shown = entries[: limits.LIST_MAX_ENTRIES]

    lines = []
    for kind, name, size, mtime, tail in shown:
        stamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        size_text = "-" if kind in ("d", "l") else _human_size(size)
        lines.append(f"{kind} {size_text:>8}  {stamp}  {name}{tail}")

    header = f"path={target}\nentries={total} shown={len(shown)}"
    if truncated:
        header += " truncated=true"
    body = "\n".join(lines) if lines else "(empty directory)"

    return {
        "text": f"{header}\n\n{body}",
        "meta": {
            "path": str(target),
            "total_entries": total,
            "shown": len(shown),
            "truncated": truncated,
        },
    }
