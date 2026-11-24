"""Запуск стенда local_datalab: проверки + docker compose up + ссылка.

По умолчанию — на переднем плане: логи в терминале, остановка через Ctrl+C
(плюс можно совсем убрать терминал). Фоновый режим: ./start_linux -d
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE_FILE = ROOT / "platform" / "compose.yaml"

sys.path.insert(0, str(ROOT))
import envlib  # noqa: E402

HUB_IMAGE = "local_datalab-jupyterhub:latest"
USER_IMAGE = "local_datalab-user:latest"


def fail(message: str) -> None:
    sys.exit(message)


def main() -> None:
    detach = "-d" in sys.argv[1:]

    if not (ROOT / ".env").exists():
        fail("Нет .env — сначала запустите ./setup_linux")

    env = envlib.load()
    if env.get("HOST_BASE_DIR") != str(ROOT):
        print(
            "Предупреждение: HOST_BASE_DIR в .env не совпадает с реальным "
            f"путём проекта ({ROOT}). Маунты могут не заработать."
        )

    if shutil.which("docker") is None:
        fail("Docker не найден — установите его и запустите ./setup_linux")
    for tag in (HUB_IMAGE, USER_IMAGE):
        if subprocess.run(
            ["docker", "image", "inspect", tag], capture_output=True
        ).returncode != 0:
            fail(f"Образ {tag} не собран — запустите ./setup_linux")

    up_cmd = ["docker", "compose", "-f", str(COMPOSE_FILE),
              "--env-file", str(ROOT / ".env"), "up"]
    if detach:
        subprocess.run([*up_cmd, "-d"], check=True)
        print(f"Стенд в фоне: http://localhost:{env.get('HUB_PORT', '8000')}")
        print("Остановка: docker compose -f platform/compose.yaml down")
    else:
        # передний план: Ctrl+C останавливает контейнеры
        print(f"Стенд: http://localhost:{env.get('HUB_PORT', '8000')}  "
              "(Ctrl+C — остановить)")
        try:
            subprocess.run(up_cmd, check=True)
        except KeyboardInterrupt:
            pass  # compose уже погасил контейнеры, traceback не нужен
        print("Стенд остановлен")


if __name__ == "__main__":
    main()
