"""Разовые тесты agent_config.py на временных каталогах.

Реальные конфиги агентов не трогаем: пути подменяются через GIGACODE_HOME /
ZCODE_CONFIG, а для сценария «агентов нет» — через USERPROFILE.

Запуск: mcp_server/.venv/Scripts/python.exe .for_agent/test/test_agent_config.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "mcp_server" / "setup"))

import agent_config  # noqa: E402

CONTEXT = {
    "venv_python": str(PROJECT / "mcp_server" / ".venv" / "Scripts" / "python.exe"),
    "mcp_dir": str(PROJECT / "mcp_server"),
}
MAIN_PY = str(Path(CONTEXT["mcp_dir"]) / "main.py")

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("[PASS] " if condition else "[FAIL] ") + name + ("" if condition else f" — {detail}"))
    if not condition:
        failures.append(name)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def case_gigacode() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        path = home / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "$version": 3,
                    "theme": "dark",
                    "permissions": {"allow": ["Bash", "mcp__other"]},
                    "mcpServers": {"other": {"command": "x"}},
                }
            ),
            encoding="utf-8",
        )
        status = agent_config.configure_gigacode(home, CONTEXT)
        data = load(path)
        entry = data["mcpServers"]["datalab"]

        check("gigacode: сервер добавлен", entry["command"] == CONTEXT["venv_python"], status)
        check("gigacode: args = main.py", entry["args"] == [MAIN_PY], status)
        check("gigacode: только command/args", set(entry) == {"command", "args"}, str(entry))
        check("gigacode: чужой сервер цел", data["mcpServers"]["other"] == {"command": "x"})
        check("gigacode: чужие ключи целы", data.get("theme") == "dark" and data.get("$version") == 3)
        check("gigacode: право добавлено", "mcp__datalab" in data["permissions"]["allow"])
        check("gigacode: чужие права целы", "Bash" in data["permissions"]["allow"])

        before = path.read_bytes()
        status = agent_config.configure_gigacode(home, CONTEXT)
        check(
            "gigacode: повтор идемпотентен",
            status == "gigacode: уже настроено" and path.read_bytes() == before,
            status,
        )


def case_gigacode_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        status = agent_config.configure_gigacode(home, CONTEXT)
        data = load(home / "settings.json")
        check(
            "gigacode: пустой каталог — файл создан",
            data["mcpServers"]["datalab"]["args"] == [MAIN_PY]
            and data["permissions"]["allow"] == ["mcp__datalab"],
            status,
        )


def case_zcode() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cli" / "config.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"plugins": {"x": True}, "mcp": {"servers": {"other": {"command": "y"}}}}),
            encoding="utf-8",
        )
        status = agent_config.configure_zcode(path, CONTEXT)
        data = load(path)
        entry = data["mcp"]["servers"]["datalab"]

        check("ZCode: сервер добавлен", entry["command"] == CONTEXT["venv_python"], status)
        check("ZCode: args = main.py", entry["args"] == [MAIN_PY], status)
        check("ZCode: type=stdio", entry.get("type") == "stdio", str(entry))
        check("ZCode: только известные поля", set(entry) == {"type", "command", "args"}, str(entry))
        check(
            "ZCode: чужие данные целы",
            data["plugins"] == {"x": True} and data["mcp"]["servers"]["other"] == {"command": "y"},
        )

        before = path.read_bytes()
        status = agent_config.configure_zcode(path, CONTEXT)
        check(
            "ZCode: повтор идемпотентен",
            status == "ZCode: уже настроено" and path.read_bytes() == before,
            status,
        )


def case_broken() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        gigacode = home / "settings.json"
        gigacode.write_text("{oops", encoding="utf-8")
        before = gigacode.read_bytes()
        status = agent_config.configure_gigacode(home, CONTEXT)
        check("gigacode: битый JSON не тронут", gigacode.read_bytes() == before and "пропущено" in status, status)

        zcode = home / "config.json"
        zcode.write_text("[]", encoding="utf-8")
        before = zcode.read_bytes()
        status = agent_config.configure_zcode(zcode, CONTEXT)
        check("ZCode: не-объект не тронут", zcode.read_bytes() == before and "пропущено" in status, status)

        gigacode.write_text(json.dumps({"mcpServers": []}), encoding="utf-8")
        before = gigacode.read_bytes()
        status = agent_config.configure_gigacode(home, CONTEXT)
        check("gigacode: mcpServers не объект", gigacode.read_bytes() == before and "пропущено" in status, status)


def case_both_and_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gigacode = root / "gigacode"
        zcode = root / "zcode" / "cli" / "config.json"
        os.environ["GIGACODE_HOME"] = str(gigacode)
        os.environ["ZCODE_CONFIG"] = str(zcode)
        try:
            status = agent_config.configure_agent(CONTEXT)
            check(
                "оба агента найдены и настроены",
                "gigacode:" in status and "ZCode:" in status
                and (gigacode / "settings.json").is_file() and zcode.is_file(),
                status,
            )
            status = agent_config.configure_agent(CONTEXT)
            check("оба: повтор идемпотентен", "уже настроено" in status and "ZCode: уже настроено" in status, status)
        finally:
            os.environ.pop("GIGACODE_HOME", None)
            os.environ.pop("ZCODE_CONFIG", None)

        old = {key: os.environ.get(key) for key in ("USERPROFILE", "HOME")}
        os.environ["USERPROFILE"] = str(root / "empty-home")
        os.environ["HOME"] = str(root / "empty-home")
        try:
            status = agent_config.configure_agent(CONTEXT)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        check("агентов нет — не ошибка", status == "агенты не найдены (gigacode/ZCode)", status)


def main() -> int:
    case_gigacode()
    case_gigacode_empty()
    case_zcode()
    case_broken()
    case_both_and_none()
    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
