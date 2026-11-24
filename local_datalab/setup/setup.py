"""Настройка стенда local_datalab (идемпотентно: повторный запуск ничего не ломает).

Что делает:
1. Создаёт .env из .env.example, если его нет (HOST_BASE_DIR подставляет сам).
2. Создаёт .venv, если его нет (скрипты проекта работают на stdlib — venv задел
   на будущее).
3. Проверяет docker и docker compose: при отсутствии печатает инструкцию
   и выходит (установку выполняет пользователь).
4. Собирает образы jupyterhub и user-image, если их нет.
5. Создаёт persistent/ и workspace/, если их нет.
"""

import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
COMPOSE_FILE = ROOT / "platform" / "compose.yaml"
USER_IMAGE_DIR = ROOT / "platform" / "user-image"

HUB_IMAGE = "local_datalab-jupyterhub:latest"
USER_IMAGE = "local_datalab-user:latest"

# Какую строку из .env.example заменяем реальным путём проекта
BASE_DIR_PLACEHOLDER = "/absolute/path/to/local_datalab"


def ensure_env() -> None:
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"
    if env_path.exists():
        return
    if not example.exists():
        sys.exit("Нет ни .env, ни .env.example — не из чего создать .env")
    text = example.read_text(encoding="utf-8").replace(
        BASE_DIR_PLACEHOLDER, str(ROOT)
    )
    env_path.write_text(text, encoding="utf-8")
    print(f"Создан .env из .env.example (HOST_BASE_DIR = {ROOT})")
    print("Проверьте .env: порт и имя сети можно поменять.")


def create_venv() -> None:
    if (VENV_DIR / "bin" / "python").exists():
        return
    print("Создаю .venv ...")
    venv.create(VENV_DIR, with_pip=True)


def check_docker() -> None:
    if shutil.which("docker") is None:
        print("Docker не найден. Установите его и запустите setup снова:")
        print("  https://docs.docker.com/engine/install/ubuntu/")
        sys.exit(1)
    r = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print("Docker есть, а `docker compose` — нет (нужен Compose v2).")
        print("  sudo apt-get install docker-compose-plugin")
        sys.exit(1)


def image_exists(tag: str) -> bool:
    return subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
    ).returncode == 0


def build_images() -> None:
    missing = [t for t in (HUB_IMAGE, USER_IMAGE) if not image_exists(t)]
    if not missing:
        print("Образы уже собраны")
        return
    print("Собираю образы:", ", ".join(missing))
    # hub — через compose (там же подхватывается его Dockerfile)
    if not image_exists(HUB_IMAGE):
        subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE),
             "--env-file", str(ROOT / ".env"), "build"],
            check=True,
        )
    # user-image — не сервис compose (его нельзя поднимать как контейнер),
    # поэтому собираем напрямую
    if not image_exists(USER_IMAGE):
        subprocess.run(
            ["docker", "build", "-t", USER_IMAGE, str(USER_IMAGE_DIR)], check=True
        )


def ensure_dirs() -> None:
    for name in ("persistent", "workspace"):
        (ROOT / name).mkdir(exist_ok=True)
    readme = ROOT / "workspace" / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Стартовая папка notebook'ов — монтируется в контейнер "
            "как /home/datalab/nfs\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    print(f"Настройка стенда: {ROOT}")
    ensure_env()
    create_venv()
    check_docker()
    build_images()
    ensure_dirs()
    print("Окружение готово. Запуск: ./start_linux")
