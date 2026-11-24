"""Поиск: glob и grep.

Оба инструмента ходят по дереву сами (os.walk), чтобы не заходить в
`.git`, `__pycache__`, `.venv` и подобные каталоги: на NFS это разница
между мгновенным ответом и минутой ожидания.
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from core import limits, paths
from core.config import Config
from core.errors import ToolError
from core.spill import write_spill


def _is_ignored_dir(name: str) -> bool:
    return name in limits.IGNORED_DIRS or name.startswith(".")


def _walk_files(root: Path):
    """Файлы под root без захода в игнорируемые и скрытые каталоги."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _is_ignored_dir(d))
        for name in sorted(filenames):
            yield Path(dirpath) / name


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Перевод glob-шаблона в регулярку с поддержкой `**`."""
    out: list[str] = []
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char == "*":
            if pattern.startswith("**/", index):
                out.append("(?:[^/]+/)*")
                index += 3
                continue
            if pattern.startswith("**", index):
                out.append(".*")
                index += 2
                continue
            out.append("[^/]*")
            index += 1
            continue
        if char == "?":
            out.append("[^/]")
            index += 1
            continue
        if char == "[":
            end = pattern.find("]", index + 1)
            if end == -1:
                out.append(re.escape(char))
                index += 1
                continue
            body = pattern[index + 1 : end]
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append(f"[{body}]")
            index = end + 1
            continue
        out.append(re.escape(char))
        index += 1
    return re.compile("^" + "".join(out) + "$")


def glob_search(
    config: Config,
    pattern: str,
    path: str,
    limit: int = limits.SEARCH_MAX_RESULTS,
) -> dict[str, Any]:
    if not pattern or not pattern.strip():
        raise ToolError("bad_request", "pattern is required", "Например: **/*.py")
    if limit < 1:
        raise ToolError("bad_request", "limit must be >= 1")
    limit = min(limit, limits.SEARCH_MAX_RESULTS)

    root = paths.require_dir(paths.resolve_read(path))
    regex = _glob_to_regex(pattern.strip())

    matches: list[tuple[float, Path]] = []
    scanned = 0
    scan_truncated = False
    for candidate in _walk_files(root):
        scanned += 1
        if scanned > limits.SEARCH_MAX_FILES:
            scan_truncated = True
            break
        relative = candidate.relative_to(root).as_posix()
        if not regex.match(relative):
            continue
        try:
            mtime = candidate.stat().st_mtime
        except OSError:
            continue
        matches.append((mtime, candidate))

    matches.sort(key=lambda item: item[0], reverse=True)
    truncated = len(matches) > limit
    shown = matches[:limit]

    lines = [str(item[1]) for item in shown]
    header = (
        f"path={root}\npattern={pattern} matches={len(matches)} "
        f"shown={len(shown)} scanned_files={scanned}"
    )
    if truncated:
        header += " truncated=true"
    if scan_truncated:
        header += " scan_truncated=true"
    body = "\n".join(lines) if lines else "(no matches)"

    meta: dict[str, Any] = {
        "path": str(root),
        "pattern": pattern,
        "matches": len(matches),
        "shown": len(shown),
        "truncated": truncated,
        "scanned_files": scanned,
        "scan_truncated": scan_truncated,
        "spill": None,
    }
    if truncated:
        meta["spill"] = str(write_spill(config, "glob", "\n".join(str(m[1]) for m in matches)))

    return {"text": f"{header}\n\n{body}", "meta": meta}


def grep_search(
    config: Config,
    pattern: str,
    path: str,
    include: str | None = None,
    literal: bool = False,
    limit: int = limits.SEARCH_MAX_RESULTS,
) -> dict[str, Any]:
    if not pattern:
        raise ToolError("bad_request", "pattern is required")
    if limit < 1:
        raise ToolError("bad_request", "limit must be >= 1")
    limit = min(limit, limits.SEARCH_MAX_RESULTS)

    root = paths.require_dir(paths.resolve_read(path))
    try:
        regex = re.compile(re.escape(pattern) if literal else pattern)
    except re.error as exc:
        raise ToolError(
            "bad_request",
            f"invalid regular expression: {exc}",
            "Для поиска подстроки передайте literal=true.",
        ) from exc

    hits: list[str] = []
    scanned = 0
    skipped_large = 0
    scan_truncated = False

    for candidate in _walk_files(root):
        if include and not fnmatch.fnmatch(candidate.name, include):
            continue
        scanned += 1
        if scanned > limits.SEARCH_MAX_FILES:
            scan_truncated = True
            break
        try:
            size = candidate.stat().st_size
        except OSError:
            continue
        if size > limits.SEARCH_MAX_FILE_BYTES:
            skipped_large += 1
            continue

        relative = candidate.relative_to(root).as_posix()
        try:
            handle = open(candidate, "rb")
        except OSError:
            continue
        with handle:
            head = handle.read(limits.BINARY_SNIFF_BYTES)
            if b"\x00" in head:
                continue
            handle.seek(0)
            for lineno, raw in enumerate(handle, 1):
                text = raw.decode("utf-8", "replace").rstrip("\r\n")
                if len(text) > limits.SEARCH_MAX_LINE_CHARS:
                    text = text[: limits.SEARCH_MAX_LINE_CHARS] + " …"
                if regex.search(text):
                    hits.append(f"{relative}:{lineno}:{text}")
                    if len(hits) >= limit:
                        break
        if len(hits) >= limit:
            break

    truncated = len(hits) >= limit
    header = (
        f"path={root}\npattern={pattern} include={include or '*'} "
        f"matches={len(hits)} scanned_files={scanned}"
    )
    if truncated:
        header += " truncated=true"
    if scan_truncated:
        header += " scan_truncated=true"
    if skipped_large:
        header += f" skipped_large_files={skipped_large}"
    body = "\n".join(hits) if hits else "(no matches)"

    meta: dict[str, Any] = {
        "path": str(root),
        "pattern": pattern,
        "include": include,
        "literal": literal,
        "matches": len(hits),
        "truncated": truncated,
        "scanned_files": scanned,
        "scan_truncated": scan_truncated,
        "skipped_large_files": skipped_large,
        "spill": None,
    }
    if truncated:
        meta["spill"] = str(write_spill(config, "grep", "\n".join(hits)))

    return {"text": f"{header}\n\n{body}", "meta": meta}
