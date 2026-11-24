"""Проверка и разрешение путей.

Правила (см. план):
- принимаются только абсолютные POSIX-пути;
- чтение не ограничивается областями;
- запись разрешена только внутри проектных областей;
- symlink, ведущий за пределы области, считается выходом за пределы области,
  потому что путь разрешается через resolve() до проверки.
"""
from __future__ import annotations

from pathlib import Path

from core.config import Config
from core.errors import ToolError


def _as_path(path: str) -> Path:
    if path is None or not isinstance(path, str) or not path.strip():
        raise ToolError(
            "bad_path",
            "path is required",
            "Передайте абсолютный POSIX-путь, например /home/datalab/project/file.py",
        )
    if "\x00" in path:
        raise ToolError("bad_path", "path contains NUL byte")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ToolError(
            "not_absolute",
            f"path must be absolute: {path}",
            "Относительные пути не поддерживаются: сервер без состояния и без "
            "рабочего каталога. Возьмите абсолютный путь из workspace_info.",
        )
    return candidate


def resolve_read(path: str) -> Path:
    """Путь для чтения: абсолютный и разрешённый, без ограничений по областям."""
    return _as_path(path).resolve()


def resolve_write(path: str, config: Config) -> Path:
    """Путь для записи: абсолютный, разрешённый и внутри одной из областей."""
    resolved = _as_path(path).resolve()
    for workspace in config.workspaces:
        try:
            resolved.relative_to(workspace.path)
        except ValueError:
            continue
        return resolved
    raise ToolError(
        "outside_workspace",
        f"write outside workspaces is not allowed: {resolved}",
        f"Доступные области: {config.workspace_names()}",
    )


def relative_to_workspace(path: Path, config: Config) -> str:
    """Короткое имя для вывода: путь относительно области, если он в ней."""
    for workspace in config.workspaces:
        try:
            return f"{workspace.name}/{path.relative_to(workspace.path).as_posix()}"
        except ValueError:
            continue
    return str(path)


def require_dir(path: Path, what: str = "path") -> Path:
    if not path.exists():
        raise ToolError("not_found", f"{what} not found: {path}")
    if not path.is_dir():
        raise ToolError(
            "not_a_directory",
            f"{what} is not a directory: {path}",
            "Для чтения файла используйте read_file.",
        )
    return path


def require_file(path: Path, what: str = "file") -> Path:
    if not path.exists():
        raise ToolError("not_found", f"{what} not found: {path}")
    if path.is_dir():
        raise ToolError(
            "is_directory",
            f"{what} is a directory: {path}",
            "Для содержимого каталога используйте list_dir.",
        )
    return path
