# local_datalab — локальная имитация datalab

JupyterHub в Docker + спавн пользовательских контейнеров (DockerSpawner).
Стенд для отработки `server/` и `mcp_server` из datalab_mcp без реального datalab.

## Быстрый старт

```bash
./setup_linux    # один раз: .env, .venv, проверки, сборка образов
./start_linux    # каждый раз: поднять стенд → http://localhost:<HUB_PORT из .env>
```

Стенд работает прямо в терминале — **Ctrl+C его останавливает**.
Фоновый режим: `./start_linux -d` (остановка: `docker compose -f platform/compose.yaml down`).

Логин — любой. Контейнер пользователя спавнится автоматически при входе.

## Структура

- `platform/` — стенд: compose.yaml, Dockerfile'ы hub и user-image, конфиг hub
- `setup/` — настройка окружения (идемпотентно)
- `setup_linux` — находит python ≥ 3.10 (PATH → pyenv → пути → вручную),
  запускает `setup/setup.py`
- `start_linux` — запуск через `.venv/bin/python` (создаётся setup'ом)
- `start.py` — логика запуска: проверки + compose up -d + ссылка
- `envlib.py` — парсер .env (stdlib, без dotenv)
- `persistent/` — домашние папки пользователей (вне git)
- `workspace/` — стартовая папка notebook'ов = `/home/datalab/nfs` (вне git)

Параметры запуска — в `.env` (шаблон: `.env.example`).
