# INDEX — datalab_mcp

MCP-инструменты для работы агента с проектными областями на datalab (jupyterhub).
Две части: `server/` (FastAPI на datalab) и `mcp_server/` (stdio MCP у агента).

## Текущее состояние
- Обе части реализованы; шаг цикла 3 закрыт.
- `server/`: 47 passed / 12 skipped на Windows (POSIX-тесты не гонялись).
- `mcp_server/`: 34 passed; end-to-end по stdio против локального `server/` проверен.
- На реальном datalab ничего ещё не запускалось.

## Следующее (в порядке)
1. Прогнать `pytest` в `server/` на Ubuntu — закрыть 12 POSIX-тестов
   (bash, сохранение mode, symlink-выход). Ошибки — сюда же.
2. Развернуть `server/` на datalab: `WORKSPACES="name=/abs/path;..."`, `PORT`,
   `python app.py`; проверить `curl` (пример в `server/README.md`).
3. Подключить `mcp_server/` к агенту с реальным `DATALAB_URL`/`DATALAB_TOKEN`
   (фрагмент конфига в `mcp_server/README.md`), проверить `workspace_info`.

## Файлы
- [context.md](context.md) — архитектура, решения, стек, что где лежит. **Читать первым.**
- [plan-tools.md](plan-tools.md) — часть 2: контракты 8 тулов, HTTP API, коды ошибок (done).
- [plan-mcp_server.md](plan-mcp_server.md) — часть 1: структура MCP-сервера,
  находки по SDK, итоги проверки (done).

## Правила работы
- Перед предложениями читать context.md и нужный план; не пересматривать
  решения (абсолютные пути, без Roots, без job-режима) без нового решения пользователя.
- Проверка кода — только на Ubuntu пользователя; на Windows прогоняется
  `mcp_server/` и часть `server/`.
- Коммиты делает пользователь.
