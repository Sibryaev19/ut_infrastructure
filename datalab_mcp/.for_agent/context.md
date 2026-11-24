# context.md

## Суть
Агент живёт на машине пользователя, а разработка — на datalab (jupyterhub, Linux).
Между ними два своих куска: MCP-сервер у агента и HTTP-сервер инструментов на
datalab. Всё реализовано; осталась проверка на реальном datalab.

## Архитектура
```
Агент --stdio/MCP--> mcp_server/ (машина агента)
                        --HTTPS + Authorization: token ...-->
                  datalab: токен проверяет платформа
                        --> server/ (FastAPI: файлы + bash)
```
- **`server/`** — вся логика: пути, лимиты, запись, поиск, терминал. Без состояния,
  без проверки токена (авторизация — на платформе).
- **`mcp_server/`** — только транспорт: тул = `POST /tools/<name>`, ошибки datalab
  превращаются в `isError` с текстом `error=/message=/hint=`.
- Внешний прокси писать не нужно — он уже стоит на datalab.

## Где что лежит
- `server/` — `app.py` (роуты), `core/` (config, limits, errors, paths, spill),
  `tools/` (fs, search, shell, info), `tests/`, README.
- `mcp_server/` — `main.py` (stdio, instructions), `src/config.py`,
  `src/datalab/` (переиспользуемый клиент + ошибки), `src/handlers/`,
  `src/tools/registration.py` (8 `@mcp.tool`), `tests/`, README.

## Ключевые решения
- Инструменты v1: `workspace_info`, `list_dir`, `read_file`, `write_file`,
  `edit_file`, `glob`, `grep`, `bash`. Без delete/move/mkdir и job-режима.
- Только POSIX-абсолютные пути; сервер без сессии и без «активного каталога».
- Чтение не ограничено областями, запись — только внутри `WORKSPACES`.
  Граница — защита от ошибок, а не песочница (`bash` пишет куда угодно).
- Области задаются env `WORKSPACES="name=/abs/path;..."`. MCP Roots не используем
  (deprecated, SEP-2577).
- `bash` по таймауту убивает группу процессов и отдаёт 200 с `timed_out: true`
  и частичным выводом — намеренное отклонение от «504».
- `write_file`/`edit_file` атомарны, сохраняют mode, поддерживают
  `expected_mtime_ms` → `stale_file`.
- Контракты и лимиты — в планах, детали реализации — в README обеих частей.

## Стек
- Python ≥ 3.10 (в коде `str | None`).
- `server/`: fastapi 0.165.0, uvicorn 0.54.0, anyio, pydantic 2.14.4.
- `mcp_server/`: `mcp==2.3.0` (сервер — `MCPServer`, не `FastMCP`), httpx 0.28.1,
  python-dotenv. `ToolError` — из `mcp.server.mcpserver.exceptions`.

## Проверка
- `server/`: на Windows 47 passed, 12 skipped (POSIX: bash, mode, symlink).
  На Ubuntu должен пройти полностью — это первое, что нужно сделать.
- `mcp_server/`: 34 passed; плюс end-to-end по stdio против локально поднятого
  `server/` (список тулов, read/write, отказ вне области, bash).

## Окружение
- У агента Windows + Git Bash; корень git-репозитория — `funny_projects`
  (коллекция pet-проектов), `datalab_mcp` внутри него.
- `.for_agent/` храним в репозитории (решение в корневом INDEX).

## Внешние ориентиры (исследовано 2026-11-23)
- MCP Roots deprecated (SEP-2577): не механизм контроля доступа; вместо них —
  явные пути в параметрах + конфиг сервера.
- DeepSeek Harness (`dsh`): одна сессия = один проект; запись фехтуется корнем,
  чтение нет; `bash` — свежая оболочка + `workdir`; `edit` — уникальное совпадение.
- OpenCode: абсолютные пути; unique match / replaceAll; `shell(command, workdir, timeout)`.
- Claude Code: `Read(offset,limit)`, `Edit(...)` с read-before-edit; cwd персистится
  только внутри проекта.
- MCP filesystem server: allow-list каталогов, symlink-выход запрещён.

## Что взято из datalab_data_transfer
Схема тонкого httpx-слоя, `Authorization: token <token>`, разбор `VERIFY_TLS`,
извлечение `detail`/`error` из ответов, подход `safe_rel_path` (стал мультикорневым).
