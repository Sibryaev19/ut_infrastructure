# План: оформление проекта (структура + .env + setup + start)

Статус: **done** (2026-11-25; проверено: setup идемпотентен, start поднимает
стенд, логин → спавн → маунты workspace/persistent → контейнер удалён при stop)
Задача: переоформить проект под удобный клиентский путь (см. context.md,
раздел «Виденье оформления»).

## Цель
`local_datalab/` — папка с папками: стенд в `platform/`, рядом будущие фичи.
Запуск и настройка — двумя командами: `setup` → `start`. Все параметры — в .env.

## Целевая структура
```
local_datalab/
├── .env.example        # в git
├── .env                # из example (gitignore)
├── .gitignore          # расширенный
├── README.md           # клиентский путь
├── envlib.py           # свой парсер .env (stdlib)
├── start.py            # проверки + docker compose up -d + ссылка
├── start_linux         # 2 строки bash: python3 start.py
├── setup/
│   └── setup.py        # venv, docker-проверки, сборка образов, .env
├── platform/           # текущий стенд целиком
│   ├── compose.yaml
│   ├── jupyterhub/     # Dockerfile + jupyterhub_config.py
│   └── user-image/
├── persistent/         # данные (gitignore)
├── workspace/          # стартовая папка notebook'ов (gitignore)
└── .for_agent/
```

## Параметры .env
- `HOST_BASE_DIR` — абсолютный путь к проекту на хосте (для маунтов и конфига hub).
- `HUB_PORT` — порт хоста (сейчас 8000).
- `NETWORK_NAME` — docker-сеть (сейчас local_datalab_datalab).
- Плюс служебные для setup/start (имена образов, папок) — по месту.

## Чек-лист
1. [x] Перенести compose.yaml, jupyterhub/, user-image/ → platform/.
2. [x] compose.yaml: захардкоженные значения → ${HOST_BASE_DIR}, ${HUB_PORT},
       ${NETWORK_NAME}. Нюанс: compose с -f ищет .env рядом с файлом, поэтому
       setup/start всегда передают --env-file <корень>/.env явно.
3. [x] jupyterhub_config.py: _base_host и имя сети из os.environ
       (передаются через environment в compose); внутренний порт всегда 8000.
4. [x] envlib.py — свой парсер KEY=VALUE (комментарии, пустые строки,
       пробелы; без кавычек-магии).
5. [x] setup/setup.py, идемпотентно: .env из example (HOST_BASE_DIR
       автоподстановкой), .venv, проверка docker (без установки),
       сборка образов, persistent/ + workspace/ + README.txt.
       Нюанс: user-image — не сервис compose (иначе up поднимал бы его),
       собирается прямым docker build -t local_datalab-user:latest.
6. [x] start.py: проверки (.env, docker, образы) → compose up -d → ссылка.
7. [x] start_linux — компактный (cd + exec python3 start.py).
8. [x] .gitignore: .env, .venv/, workspace/, persistent/, python- и IDE-мусор.
9. [x] README.md: краткий — клиентский путь + список папок.
10. [x] Проверка полного цикла: setup ×2 → start → логин tester → спавн →
        маунты workspace + persistent → docker stop → контейнер удалён.
        Тестовый след (persistent/jupyter-tester) убран; test_app.py не тронут.

## Вне объёма (будущее, отдельными задачами)
- stop-скрипт, idle_culler, форма выбора образа/настроек контейнера,
  кастомное оформление.
