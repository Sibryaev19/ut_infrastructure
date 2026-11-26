# INDEX — datalab_mcp

MCP-инструменты для работы агента с проектными областями на datalab (jupyterhub).
Две части: `server/` (FastAPI на datalab) и `mcp_server/` (stdio MCP у агента).

## Текущее состояние
- Обе части реализованы; шаг цикла 3 закрыт.
- `server/`: 47 passed / 12 skipped на Windows (POSIX-тесты не гонялись).
- `mcp_server/`: 34 passed; e2e по stdio проверен и против живого стенда.
- СТЕНД (2026-11-25): server/ поднят в контейнере пользователя local_datalab
  (`python start_server.py`, config из env.txt: WORKSPACE=/home/datalab/nfs/test,
  порт 9999). Доступ с хоста — через прокси hub с токеном:
  `http://<host>:8000/user/batsen/proxy/9999`.
- E2E ПРОТИВ СТЕНДА ПРОЙДЕН (2026-11-25): 8/8 тулов по MCP-stdio
  (скрипт `.for_agent/test/e2e_mcp_stand.py`). mcp_server подключён к ZCode
  workspace-конфигом `funny_projects/.zcode/config.json` — в новых чатах
  проекта тулзы datalab доступны автоматически.

- SETUP (2026-11-25): `mcp_server/setup.bat` + `mcp_server/setup/setup.py` готовы —
  поиск Python ≥ 3.10, venv `mcp_server/.venv`, установка из корпоративного
  pypi или интернета (pip пропускается, если пины уже стоят), отчёт.
  Интернет-режим прогнан вживую; корпоративный — на целевой машине.

- AGENT CONFIG (2026-11-25): setup прописывает `datalab` в gigacode
  (`~/.gigacode/settings.json` + право `mcp__datalab`) и ZCode
  (`~/.zcode/cli/config.json`). Проверено на временных каталогах, реальные
  конфиги ноутбука не менялись.

- РЕАЛЬНЫЙ DATALAB (2026-11-25): цепочка работает в контуре без доработок.
  Ручной шаг — только заполнить `mcp_server/.env`; `setup.bat` поставил venv,
  зависимости и прописал gigacode.

## Следующее (в порядке)
1. «Чистый агент» (новый чат) уже тестировал тула — отчёт принят, найденный
   «баг» CRLF не воспроизвёлся; depth из list_dir выпилен (2026-11-25,
   pytest: server 59 passed / Ubuntu без скипов, mcp 34 passed, e2e ALL PASS).

## Активная задача
- Нет. Предыдущая (автопрописка MCP у gigacode/ZCode) закрыта 2026-11-25.

## Файлы
- [context.md](context.md) — архитектура, решения, стек, что где лежит. **Читать первым.**
- [plan-tools.md](plan-tools.md) — часть 2: контракты 8 тулов, HTTP API, коды ошибок (done).
- [plan-mcp_server.md](plan-mcp_server.md) — часть 1: структура MCP-сервера,
  находки по SDK, итоги проверки (done).

## Правила работы
- Код `server/` тестируется в копии внутри стенда
  `../local_datalab/workspace/server`; любая доработка вносится в ОБА места
  (копия + этот проект), оригинал — источник правды.
- Перед предложениями читать context.md и нужный план; не пересматривать
  решения (абсолютные пути, без Roots, без job-режима) без нового решения пользователя.
- Проверка кода — только на Ubuntu пользователя; на Windows прогоняется
  `mcp_server/` и часть `server/`.
- Коммиты делает пользователь.
