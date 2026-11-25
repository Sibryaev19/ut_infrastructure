"""Регистрация MCP-сервера datalab в конфигах агентов.

Поддерживаются два агента:
  - gigacode: ~/.gigacode/settings.json -> mcpServers.datalab
    + permissions.allow["mcp__datalab"], чтобы не подтверждать каждый вызов;
  - ZCode: ~/.zcode/cli/config.json -> mcp.servers.datalab (stdio).

Пути переопределяются для тестов: GIGACODE_HOME (каталог .gigacode) и
ZCODE_CONFIG (файл config.json). Бэкапы не делаем: правка точечная, чужие
ключи и серверы сохраняются, повреждённый JSON не перезаписывается.

env в записи не задаём: mcp_server сам читает .env рядом со своим main.py
(путь считается от файла, а не от cwd), поэтому секреты в конфиг агента
не попадают.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

SERVER_KEY = "datalab"
PERMISSION_RULE = f"mcp__{SERVER_KEY}"


def _home() -> Path:
    return Path.home()


def gigacode_home() -> Path:
    override = os.environ.get("GIGACODE_HOME")
    return Path(override).expanduser() if override else _home() / ".gigacode"


def zcode_config_path() -> Path:
    override = os.environ.get("ZCODE_CONFIG")
    return Path(override).expanduser() if override else _home() / ".zcode" / "cli" / "config.json"


def _load_object(path: Path) -> tuple[dict[str, Any] | None, str]:
    """(данные, "") или (None, причина): битый файл не трогаем."""
    if not path.exists():
        return {}, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, f"не читается: {exc}"
    if not isinstance(data, dict):
        return None, "в корне не JSON-объект"
    return data, ""


def _write_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _server_entry(context: Mapping[str, Any], *, with_type: bool) -> dict[str, Any]:
    """Запись stdio-сервера. У ZCode схема строгая, поэтому только известные поля."""
    mcp_dir = Path(str(context["mcp_dir"]))
    entry: dict[str, Any] = {}
    if with_type:
        entry["type"] = "stdio"
    entry["command"] = str(context["venv_python"])
    entry["args"] = [str(mcp_dir / "main.py")]
    return entry


def configure_gigacode(home_dir: Path, context: Mapping[str, Any]) -> str:
    path = home_dir / "settings.json"
    data, problem = _load_object(path)
    if data is None:
        return f"gigacode: пропущено — {path} {problem}"

    servers = data.get("mcpServers")
    if servers is None:
        servers = data["mcpServers"] = {}
    if not isinstance(servers, dict):
        return f"gigacode: пропущено — mcpServers в {path.name} не объект"

    notes: list[str] = []
    changed = False

    entry = _server_entry(context, with_type=False)
    if servers.get(SERVER_KEY) != entry:
        servers[SERVER_KEY] = entry
        notes.append("сервер datalab")
        changed = True

    permissions = data.get("permissions")
    if permissions is None:
        permissions = data["permissions"] = {}
    if not isinstance(permissions, dict):
        notes.append(f"permissions не объект, правило {PERMISSION_RULE} не добавлено")
    else:
        allow = permissions.get("allow")
        if allow is None:
            allow = permissions["allow"] = []
        if not isinstance(allow, list):
            notes.append(f"permissions.allow не список, правило {PERMISSION_RULE} не добавлено")
        elif PERMISSION_RULE not in allow:
            allow.append(PERMISSION_RULE)
            notes.append(f"право {PERMISSION_RULE}")
            changed = True

    if not notes:
        return "gigacode: уже настроено"
    if changed:
        _write_object(path, data)
    return "gigacode: " + ", ".join(notes)


def configure_zcode(path: Path, context: Mapping[str, Any]) -> str:
    data, problem = _load_object(path)
    if data is None:
        return f"ZCode: пропущено — {path} {problem}"

    mcp = data.get("mcp")
    if mcp is None:
        mcp = data["mcp"] = {}
    if not isinstance(mcp, dict):
        return f"ZCode: пропущено — mcp в {path.name} не объект"

    servers = mcp.get("servers")
    if servers is None:
        servers = mcp["servers"] = {}
    if not isinstance(servers, dict):
        return f"ZCode: пропущено — mcp.servers в {path.name} не объект"

    entry = _server_entry(context, with_type=True)
    if servers.get(SERVER_KEY) == entry:
        return "ZCode: уже настроено"
    servers[SERVER_KEY] = entry
    _write_object(path, data)
    return "ZCode: сервер datalab добавлен или обновлён"


def configure_agent(context: Mapping[str, Any]) -> str:
    """Прописать MCP-сервер во всех найденных агентах. Возвращает статус для отчёта."""
    mcp_dir = Path(str(context["mcp_dir"]))
    main_py = mcp_dir / "main.py"
    if not main_py.is_file():
        return f"не найден {main_py}"

    results: list[str] = []

    gigacode = gigacode_home()
    if os.environ.get("GIGACODE_HOME") or gigacode.is_dir():
        results.append(configure_gigacode(gigacode, context))

    zcode = zcode_config_path()
    if os.environ.get("ZCODE_CONFIG") or zcode.exists() or (_home() / ".zcode").is_dir():
        results.append(configure_zcode(zcode, context))

    if not results:
        return "агенты не найдены (gigacode/ZCode)"
    return "; ".join(results)
