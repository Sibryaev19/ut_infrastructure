# context.md — local_datalab

## Принцип пользователя (учитывать в проектировании)
Мечта/цель: автоматизация всей работы через модули → объединения модулей →
переиспользуемая личная инфраструктура + база знаний. Значит: проектировать
модульно, оформлять по единому паттерну (env/setup/start), делать пригодным
для переиспользования в будущих проектах, а не «лишь бы работало».
Эталон паттерна — lab1 (gui_labs_2026): не родился готовым, а
кристаллизовался там после постепенной эволюции предыдущих проектов.

## Цель
Одноразово собрать и переиспользовать локальный «мини-datalab»: jupyterhub
с UI в Docker, который проксирует пути в пользовательский контейнер, где
работают notebook (классика) и `server/` из datalab_mcp. Стенд для отработки
POSIX-тестов, развёртывания server/ и сквозных проверок mcp_server.

## Архитектура (черновик, согласована на шаге 1)
```
mcp_server (та же машина) → http://localhost:8000
   └─ compose: jupyterhub (UI, прокси)
        └─ DockerSpawner (через /var/run/docker.sock) → контейнер пользователя
             ├─ jupyter notebook
             ├─ server/ (FastAPI, WORKSPACES=/home/datalab/nfs/<name>)
             └─ volume: ./workspace ↔ /home/datalab/nfs (виден из проводника Windows)
```

## Связь с web_proxy (2026-11-25)
- Когда-то пользователь делал web-proxy для datalab — не получилось; проект
  лежит в ~/Desktop/ROOT/Projects/web_proxy. Его мёртвый остановленный
  контейнер `jupyterhub-imitation` (nginx) висит в docker — НЕ наш, не
  трогать без спроса.
- Пользователь любит «строить по кирпичикам» и возвращаться к старым
  проектам при новой возможности. Теперь, когда есть имитация платформы,
  вернуться к web_proxy — реалистичный будущий сценарий.

## Инфраструктурные соседи (решено 2026-11-28)
- Greenplum и HDFS — часть имитации datalab, но живут ОТДЕЛЬНЫМИ модулями
  (соседние папки в инфраструктурном монорепо, см. «Разделение монорепо»,
  паттерн env/setup/start), НЕ внутри local_datalab. Пользователь поднимает
  их руками; стенд работает и без них. У модулей свои .for_agent.
- Связка: compose модулей дополнительно подключает сервисы к docker-сети
  ${NETWORK_NAME} как external — контейнеры пользователей ходят к ним по
  именам сервисов. Порты наружу не публикуются.
- Данные модулей — в их data/ (gitignored), bind-маунты. UID образов
  (postgres/hadoop) потребует chown при первом подъёме — ритуал setup'а.
- В git модули идут: трекается только код/конфиги; data/, .env, .venv — в
  их .gitignore. Секреты — в .env, в compose.yaml только ${VAR}.

## Разделение монорепо (решено 2026-11-28)
- Набор (local_datalab, datalab_mcp, universal_toolkit, datalab_data_transfer,
  будущие gp/hdfs и далее — не только datalab) выделяется ПЕРЕИМЕНОВАНИЕМ
  монорепо funny_projects → ut_infrastructure (история сохраняется целиком,
  без filter-repo). img_translator, jira_analyzer, shit_downloader — выносятся
  в новый отдельный репозиторий funny_projects (свежий git init, история
  игрушек не переносится; описания игрушек для нового README — в истории:
  git show HEAD:README.md).
- GitHub: Sibryaev19/funny_projects переименовывается в
  Sibryaev19/ut_infrastructure; имя funny_projects освобождается для нового
  репо. Старый URL redirect'ит.
- После переезда все абсолютные пути (в .env, .for_agent, README) правятся
  на ~/Desktop/ROOT/Projects/datalab/...

## Границы имитации (решено пользователем, 2026-11-24)
- Авторизацию и проверку токена НЕ имитируем — на функционал не влияет.
  Вручную логинимся через UI (DummyAuthenticator/allow_all); bearer-токен
  при необходимости добавим позже.
- Образ пользователя — простой python:3.12 + jupyter + зависимости server/.
  Spark, kinit, fsspec и прочие детали datalab НЕ имитируем; при желании
  образ можно позже подменить на приближённый к datalab — конфиг спавнера
  не меняется.
- TLS не нужен: локально HTTP; datalab_mcp работает с VERIFY_TLS=false.
- Путь workspace в контейнере — /home/datalab/nfs/... как на datalab.

## Окружение стенда (2026-11-24, проверено)
- ХОСТ — домашний комп с Ubuntu, нативный Docker (Windows-ноутбук отброшен
  после неудачных попыток поставить WSL/Docker — история в wsl-install.md).
- Docker 29.1.3 ✅ и Docker Compose v2.40.3 ✅ — проверены, работают.
- ВСЁ на одном компе: стенд и mcp_server рядом. Сеть не нужна,
  mcp_server ходит на `http://localhost:8000`. Среда mcp_server
  (Windows/Linux) не важна — в будущем на ноуте с Windows заработает так же.
- jupyterhub-контейнеру пробрасывается docker-сокет хоста
  (`/var/run/docker.sock`) — на нативном Linux это работает без нюансов.

## Стек стенда (актуально)
- Официальный образ `jupyterhub/jupyterhub`; DockerSpawner.
- Стенд в `platform/`: compose.yaml + jupyterhub/ + user-image/.
- НЮАНС: jupyterhub_config.py копируется в образ hub при BUILD (COPY в
  Dockerfile) — правки конфига требуют `docker compose build`, пересоздания
  контейнера недостаточно (поймано 2026-11-25).
- Терминалы/сессии в контейнере открываются сразу в /home/datalab/nfs
  (2026-11-25): ServerApp.root_dir задаёт только корень файлового браузера,
  терминал наследует cwd процесса сервера → задаётся через
  c.DockerSpawner.extra_create_kwargs = {"working_dir": "/home/datalab/nfs"}
  (trait'а working_dir у DockerSpawner нет, конфиг-строка была бы
  проигнорирована). Альтернатива «в конкретной папке»: правый клик →
  Open in Terminal.
- user-image — НЕ сервис compose (up поднимал бы его контейнером):
  собирается setup'ом прямым `docker build -t local_datalab-user:latest`.
- Конфигурация — в .env корня: HOST_BASE_DIR, HUB_PORT, NETWORK_NAME.
  Compose читает через --env-file (с -f ищет .env рядом с файлом, не в cwd!),
  в hub — через environment. Внутренний порт hub всегда 8000.
- Своё: envlib.py (парсер KEY=VALUE, stdlib), setup/setup.py
  (идемпотентный), start.py.
- Запуск (решено 2026-11-25): start_linux — ПЕРЕДНИЙ план, стенд живёт
  в терминале, Ctrl+C останавливает; фоновый режим — ./start_linux -d.
  Пользователь не любит «повисшие в фоне» сервисы.
- Паттерны пользователя «setup-bash»/«start-bash» (2026-11-25):
  setup_linux ищет python ≥ 3.10 (PATH → pyenv → стандартные пути → ручной
  ввод, каждый кандидат проверяется реальным запуском) и запускает
  setup/setup.py; start_linux ничего не ищет — берёт .venv/bin/python.
  Родители паттерна: lab4/start_windows.bat, jira_analyzer/setup.bat,
  img_translator/windows/install.bat (самый продвинутый, с реестром).
  Пользователь планирует оформить паттерны в шаблоны/скиллы.

## Виденье оформления (решено пользователем, 2026-11-25)
- Вся логика — на Python (setup.py, start.py на чистом stdlib); bash —
  максимум «найти python → запустить py». Пользователь не любит сложный bash.
- Свой парсер .env (KEY=VALUE), без библиотеки dotenv.
- setup идемпотентный: проверяет, что уже сделано, и не повторяет.
- Клиентский путь: открыть папку → заполнить .env → setup (если ещё не) →
  start → получить ссылку http://localhost:<порт> → работать в браузере.
- Контейнер пользователя спавнится при логине, не поднимается руками;
  «смерть» контейнера (UI-кнопка, idle-culler, stop-скрипт) — в будущем.
- Структура: текущий стенд целиком в platform/; будущие фичи (тема,
  форма выбора образа и т.п.) — соседними папками. Тяжёлое (persistent/,
  workspace/, .env, .venv) — в .gitignore.
