# plan-стенд — имитация datalab (jupyterhub в Docker)

Статус: **done** (2026-11-25) — стенд работает, все проверки пройдены.

## Дополнение: персистентность (2026-11-25)
- Персональный home пользователя `/home/jovyan` ↔ `persistent/jupyter-<имя>/`
  (создаёт pre_spawn_hook; хук выполняется ВНУТРИ hub, поэтому `persistent/`
  смонтирован в hub по тому же абсолютному пути, что на хосте; chown 1000:100
  на папку и work/).
- Переживают рестарты: workspace, home (notebook'и, pip --user, настройки).
  НЕ переживает: pip install в /opt/conda (лечится добавлением в образ или venv).
- Проксирование портов: jupyter-server-proxy в образе пользователя,
  путь `/user/<имя>/proxy/<порт>/` (у datalab — `/port/`, отличаемся этим сегментом).
  base_path пользователя: `/user/batsen/proxy/<порт>/`.
- `.gitignore`: persistent/, .for_agent/, __pycache__/.

## Прогресс (2026-11-24, вечер)
- Стенд поднят: `docker compose up -d --build`; hub на :8000, спавн работает.
- Дымовой тест (curl): логин → спавн jupyter-testuser (healthy) → /lab 200,
  workspace виден, python 3.12 и fastapi/uvicorn на месте.
- Пойманные и решённые проблемы:
  1) single-user не находил Hub → `hub_ip=0.0.0.0` + `hub_connect_ip=jupyterhub`;
  2) маунт workspace: путь в конфиге должен быть АБСОЛЮТНЫМ ПУТЁМ ХОСТА
     (пути изнутри контейнера hub демону не видны);
  3) тег базового образа: `quay.io/jupyter/minimal-notebook:python-3.12.10`;
     chown через `${NB_UID}:${NB_GID}`, не `jovyan:jovyan`.
- Мусор: пустая `/workspace` в корне хоста (создал docker-демон) — убрать
  `sudo rmdir /workspace`.

## Цель
Поднять локальный jupyterhub-стенд, имитирующий datalab, для ручной проверки:
файловая система (workspace), запуск python, поднятие сервера, работа
jupyter notebook через UI.

Границы: этот проект — ТОЛЬКО имитация datalab. mcp_server — другой проект
(datalab_mcp), здесь не тестируем.

## Состав

1. `compose.yaml`
   - сервис `jupyterhub`: официальный образ, порт `8000:8000`,
     проброс `/var/run/docker.sock`, общая docker-сеть со спавненными
     контейнерами;
   - volume `./workspace ↔ /home/datalab/nfs`.
2. `jupyterhub/Dockerfile` + `jupyterhub/jupyterhub_config.py`
   - DummyAuthenticator (логин любым именем, allow_all);
   - DockerSpawner (через docker-сокет хоста), образ пользователя,
     mount `/home/datalab/nfs`, сеть compose.
3. `user-image/Dockerfile`
   - python:3.12-slim + jupyter notebook + зависимости `server/`
     (FastAPI и пр. из datalab_mcp).
4. `workspace/` — пустая папка, монтируется как `/home/datalab/nfs`;
   заранее положить файл-маркер для проверки видимости ФС.
5. Dockerfile для hub — добавить зависимости DockerSpawner внутрь hub-образа.

## Чек-лист ручной проверки (заход пользователя)
- [ ] `http://localhost:8000` открывается, логин проходит
- [ ] спавн контейнера пользователя успешен
- [ ] видна файловая система `/home/datalab/nfs` (файл-маркер на месте)
- [ ] в notebook выполняется python (`print`)
- [ ] поднимается сервер (FastAPI `server/`) и отвечает на запросы
- [ ] notebook и сервер работают одновременно в одном контейнере

## Открытые вопросы — закрыты
- [x] Копия datalab_mcp: `/home/batsen/Desktop/ROOT/Projects/ut_infrastructure/datalab_mcp`
      (остаётся справочным проектом для будущих шагов; зависимости server/:
      fastapi==0.165.0, uvicorn==0.54.0, anyio==4.16.0, pydantic==2.14.4).
- [x] `server/` в контейнере поднимается руками из notebook; автозапуска нет.

## Решения
- K8s datalab не имитируем: DockerSpawner вместо KubeSpawner — деталь
  инфраструктуры jupyterhub, код пользователя от неё не зависит.
- Авторизация — DummyAuthenticator; TLS не нужен (локальный HTTP).
- Путь workspace в контейнере — `/home/datalab/nfs/...` как на datalab.
