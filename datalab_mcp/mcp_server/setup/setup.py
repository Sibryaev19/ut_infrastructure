"""Установка datalab_mcp одной командой: setup.bat -> этот скрипт.

Что делает:
  1. берёт настройки из mcp_server/.env (если файла нет — копирует из
     .env.example и просит заполнить);
  2. создаёт (или переиспользует) venv mcp_server/.venv;
  3. ставит mcp_server/requirements.txt из корпоративного pypi (токен из .env)
     или из интернета — по флагу PIP_USE_CORPORATE; если все пины уже стоят
     в venv, pip не запускается;
  4. проверяет, что нужные пакеты импортируются;
  5. зовёт заглушку прописки MCP-сервера в конфиг агента;
  6. печатает итоговый отчёт.

Только stdlib: venv к этому моменту ещё нет. Python >= 3.10 (проверяет setup.bat).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

import agent_config

MCP_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = MCP_DIR.parent
VENV_DIR = MCP_DIR / ".venv"
ENV_FILE = MCP_DIR / ".env"
ENV_EXAMPLE = MCP_DIR / ".env.example"
REQUIREMENTS = MCP_DIR / "requirements.txt"

CORPORATE_INDEX_PATH = "/repo/pypi/simple"
MIN_PYTHON = (3, 10)

EXIT_OK = 0
EXIT_INSTALL = 1
EXIT_CONFIG = 2


# --- настройки ---

def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE построчно; кавычки вокруг значения срезаются."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def setting(values: dict[str, str], key: str, default: str = "") -> str:
    """Переменная окружения приоритетнее .env (удобно для разовых прогонов)."""
    return (os.environ.get(key) or values.get(key) or default).strip()


def as_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def normalize_host(raw: str) -> str:
    """'https://my_company.ru/' -> 'my_company.ru'."""
    host = raw.strip().strip("/")
    if "://" in host:
        host = urlsplit(host).netloc
    return host.split("/", 1)[0]


def ensure_env_file() -> bool:
    """Создаёт mcp_server/.env из примера. True — файл только что создан."""
    if ENV_FILE.exists():
        return False
    if not ENV_EXAMPLE.exists():
        print(f"[!] нет шаблона настроек: {ENV_EXAMPLE}")
        return False
    shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
    print(f"[+] создан {ENV_FILE} (копия .env.example)")
    print("    заполните DATALAB_URL, DATALAB_TOKEN и, если нужно, PIP_*")
    return True


# --- venv и pip ---

def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_venv() -> Path:
    python = venv_python(VENV_DIR)
    if python.exists():
        print(f"[=] venv уже есть: {VENV_DIR}")
        return python
    print(f"[+] создаю venv: {VENV_DIR}")
    code = subprocess.call([sys.executable, "-m", "venv", str(VENV_DIR)])
    if code != 0 or not python.exists():
        raise RuntimeError(f"не удалось создать venv (код {code})")
    return python


def build_install_command(python: Path, host: str, token: str) -> list[str]:
    """Команда pip install (выводится в консоль как есть, вместе с токеном)."""
    command = [str(python), "-m", "pip", "install", "--ignore-installed"]
    if host:
        index_url = f"https://token:{quote(token, safe='')}@{host}{CORPORATE_INDEX_PATH}"
        command += ["--index-url", index_url, "--trusted-host", host]
    command += ["-r", str(REQUIREMENTS)]
    return command


def install_requirements(python: Path, host: str, token: str) -> None:
    command = build_install_command(python, host, token)
    print("[>] " + " ".join(f'"{part}"' if " " in part else part for part in command))
    code = subprocess.call(command, cwd=str(MCP_DIR))
    if code != 0:
        raise RuntimeError(f"pip install завершился с кодом {code}")


def installed_versions(python: Path) -> dict[str, str]:
    """Установленные в venv дистрибутивы: нормализованное имя -> версия."""
    code = (
        "import json, importlib.metadata as md\n"
        "print(json.dumps({(d.metadata['Name'] or '').lower().replace('-', '_'): d.version"
        " for d in md.distributions()}))"
    )
    result = subprocess.run(
        [str(python), "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {}


def parse_requirement(line: str) -> tuple[str, str, str] | None:
    """'mcp==2.3.0' -> ('mcp', '==', '2.3.0'); комментарии и пустые — None."""
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    for operator in ("===", "==", ">=", "<=", "!=", "~=", ">", "<"):
        if operator in line:
            name, _, version = line.partition(operator)
            return name.strip().lower().replace("-", "_"), operator, version.strip()
    return line.lower().replace("-", "_"), "", ""


def _version_tuple(text: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", text)[:4]]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def version_satisfies(installed: str, operator: str, required: str) -> bool:
    have, want = _version_tuple(installed), _version_tuple(required)
    if not want:
        return True
    if operator in ("==", "==="):
        return have == want
    if operator == ">=":
        return have >= want
    if operator == ">":
        return have > want
    if operator == "<=":
        return have <= want
    if operator == "<":
        return have < want
    if operator == "!=":
        return have != want
    # ~= и прочие операторы не поддерживаем: пусть решает pip
    return False


def missing_requirements(python: Path) -> list[str]:
    """Пакеты из requirements.txt, которых нет в venv или версия не подходит."""
    installed = installed_versions(python)
    missing: list[str] = []
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        spec = parse_requirement(raw)
        if spec is None:
            continue
        name, operator, required = spec
        have = installed.get(name)
        if have is None:
            missing.append(name)
        elif not version_satisfies(have, operator, required):
            missing.append(f"{name} {have} (нужно {operator}{required})")
    return missing


def check_imports(python: Path) -> list[str]:
    """Проверяет ключевые пакеты и возвращает строки 'имя версия'."""
    code = (
        "import importlib.metadata as md\n"
        "import mcp, httpx, dotenv\n"
        "for name in ('mcp', 'httpx', 'python-dotenv'):\n"
        "    print(name, md.version(name))\n"
    )
    result = subprocess.run(
        [str(python), "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-5:]
        raise RuntimeError("пакеты не импортируются:\n  " + "\n  ".join(tail))
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# --- отчёт ---

def missing_agent_settings(values: dict[str, str]) -> list[str]:
    missing = []
    for key in ("DATALAB_URL", "DATALAB_TOKEN"):
        value = setting(values, key)
        # плейсхолдеры из .env.example: <наружный-адрес-datalab>, <JUPYTERHUB_API_TOKEN>
        if not value or "<" in value or ">" in value:
            missing.append(key)
    return missing


def main() -> int:
    # pip пишет напрямую в консоль: без построчной буферизации заголовок
    # отчёта окажется после его вывода
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:  # pragma: no cover
        pass

    print("== datalab_mcp setup ==")
    print(f"mcp_server: {MCP_DIR}")
    print(f"python: {sys.executable} ({sys.version.split()[0]})")

    if sys.version_info < MIN_PYTHON:
        print(f"[!] нужен Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}")
        return EXIT_CONFIG
    if not REQUIREMENTS.exists():
        print(f"[!] нет файла зависимостей: {REQUIREMENTS}")
        return EXIT_CONFIG

    ensure_env_file()
    values = read_env_file(ENV_FILE) if ENV_FILE.exists() else {}

    corporate = as_bool(setting(values, "PIP_USE_CORPORATE"))
    host = normalize_host(setting(values, "PIP_INDEX_HOST"))
    token = setting(values, "PIP_TOKEN")

    if corporate:
        absent = [name for name, value in (("PIP_INDEX_HOST", host), ("PIP_TOKEN", token)) if not value]
        if absent:
            print(f"[!] PIP_USE_CORPORATE=true, но не заполнено: {', '.join(absent)}")
            print(f"    заполните {ENV_FILE} (шаблон — {ENV_EXAMPLE.name})")
            return EXIT_CONFIG
        mode = f"корпоративный ({host})"
    else:
        mode = "интернет (pypi.org)"
    print(f"режим установки: {mode}")

    try:
        python = ensure_venv()
        missing = missing_requirements(python)
        if missing:
            print(f"[+] требуют установки: {', '.join(missing)}")
            install_requirements(python, host if corporate else "", token if corporate else "")
        else:
            print("[=] зависимости из requirements.txt уже установлены, pip пропущен")
        packages = check_imports(python)
    except RuntimeError as exc:
        print(f"[!] {exc}")
        return EXIT_INSTALL

    context = {
        "project_root": str(PROJECT_ROOT),
        "mcp_dir": str(MCP_DIR),
        "venv_python": str(python),
        "requirements": str(REQUIREMENTS),
        "env_file": str(ENV_FILE),
    }
    try:
        agent_status = agent_config.configure_agent(context)
    except Exception as exc:  # интеграция не должна валить установку
        agent_status = f"ошибка: {exc}"
        print("[!] прописка агента не удалась — venv всё равно готов")

    print()
    print("== готово ==")
    print(f"venv: {VENV_DIR}")
    print(f"режим: {mode}")
    for line in packages:
        print(f"  {line}")
    print(f"агент: {agent_status}")

    missing = missing_agent_settings(values)
    if missing:
        print()
        print(f"[!] не заполнено в {ENV_FILE.name}: {', '.join(missing)}")
        print("    MCP-сервер не сможет подключиться, пока они пустые")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
