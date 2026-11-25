"""Запуск server/ одной командой: python start_server.py.

Параметры читаются из env.txt рядом со скриптом (формат как у .env:
KEY=VALUE, # — комментарии). Найденное — дефолты: реальные переменные
окружения приоритетнее. Относительный WORKSPACE резолвится от папки
env.txt и превращается в WORKSPACES="имя=путь" (имя = имя папки).
uvicorn вписан сюда же; запуск передний план, остановка — Ctrl+C.
"""

import os
from pathlib import Path

import uvicorn

from app import build_default_app

HOST_DEFAULT = "0.0.0.0"
PORT_DEFAULT = 9999
WORKSPACE_DEFAULT = "/home/datalab/nfs"
SPILL_DIR_DEFAULT = "/tmp/datalab_mcp"


def load_env_txt(path: Path) -> dict[str, str]:
    """KEY=VALUE построчно, без внешних зависимостей."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def apply_env(values: dict[str, str], base_dir: Path) -> None:
    """env.txt как дефолты, переменные окружения не перетираем."""
    workspace = values.get("WORKSPACE", WORKSPACE_DEFAULT)
    if not os.path.isabs(workspace):
        workspace = base_dir / workspace
    workspace = os.path.abspath(workspace)
    # WORKSPACE из env.txt сильнее унаследованного окружения: контейнер
    # datalab может прийти с "голым" WORKSPACES без имени области.
    if values.get("WORKSPACE") or not os.environ.get("WORKSPACES"):
        os.environ["WORKSPACES"] = f"{os.path.basename(workspace)}={workspace}"
    os.environ.setdefault("SPILL_DIR", values.get("SPILL_DIR", SPILL_DIR_DEFAULT))

    host = values.get("HOST", HOST_DEFAULT)
    port = values.get("PORT", str(PORT_DEFAULT))
    return host, int(port)


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    host, port = apply_env(load_env_txt(base_dir / "env.txt"), base_dir)

    application = build_default_app()
    uvicorn.run(application, host=host, port=port)


if __name__ == "__main__":
    main()
