# for_windows.md — перенос проекта на Windows

Что переезжает: `mcp_server/` (агентская часть) и стенд `local_datalab`.
`server/` — НИКОГДА не запускается нативно на Windows, он живёт в Linux-контейнере
(на реальном datalab — тоже Linux). Если это правило держать, перенос почти
безболезненный.

## 1. mcp_server — переносится легко

- В конфиге агента путь к интерпретатору другой:
  `...\datalab_mcp\mcp_server\.venv\Scripts\python.exe`
- Зависимости чисто питоновские (mcp, httpx, dotenv) — Windows-совместимы.
- `.env` лежит рядом с `main.py`, путь ищется от файла, а не от cwd —
  уже работает при любом способе запуска (фикс 2026-11-25).
- Глобальный конфиг MCP переездить: `C:\Users\<user>\.zcode\cli\config.json`
  → `mcp.servers.datalab`, пути — Windows-формат.
- `DATALAB_URL` и токен — те же; если стенд тоже переехал, URL не меняется
  (`http://localhost:8000/user/<name>/proxy/<port>`).

## 2. server/ — только внутри контейнера

Всё, что сервер требует, есть в Linux-контейнере и на Windows не существует:
- POSIX-абсолютные пути (`/home/datalab/nfs/...`) — агенту это и так
  предписывают инструкции тула;
- `bash`-тул — требует bash;
- symlink, chmod/mode — поведение Linux.
Нативный запуск `start_server.py` на Windows упадёт или поведёт себя
непредсказуемо — не пробовать.

## 3. Стенд local_datalab — Docker Desktop

- Нужен Docker Desktop с WSL2-бэкендом (история борьбы — `wsl-install.md`
  в local_datalab: чистый WSL не завёлся, Docker Desktop — рабочий путь).
- `/var/run/docker.sock` маунт в hub работает через Docker Desktop без правок.
- Маунты `HOST_BASE_DIR` и `workspace/` — Windows-пути хоста Docker Desktop
  пробрасывает сам; ВНУТРИ контейнеров пути остаются Linux (`/home/datalab/nfs`)
  — jupyterhub_config.py и env.txt менять не нужно.
- `pre_spawn_hook` делает `chown 1000:100` — на NTFS-маунте может не примениться;
  некритично, следить только если будут permission-ошибки при записи.
- `setup_linux` / `start_linux` — bash-скрипты; на Windows запускать из
  Git Bash/WSL либо руками: `setup/setup.py` и `start.py` — обычный python.

## 4. CRLF — главная ловушка

- Настрой git: `core.autocrlf=input` (или `.gitattributes`: `*.py eol=lf`,
  `*.txt eol=lf`) — иначе checkout превратит LF в CRLF, и diff'ы/тесты
  поедут.
- Наши тула CRLF-безопасны: `edit_file` распознаёт CRLF и подсказывает агенту;
  тесты на CRLF-чувствительность есть в suite.
- Скрипт запуска `start_server.py` и `env.txt` на CRLF не ломаются
  (парсер env.txt делает `strip()` по строкам).

## 5. Проверка после переезда (по порядку)

1. `pytest` в `server/` — часть POSIX-тестов уйдёт в skip (маркер `posix_only`) —
   это НОРМАЛЬНО: они проверяют Linux-поведение и выполняются в контейнере стенда.
2. `pytest` в `mcp_server/` — должны пройти все.
3. Стенд: `./start_linux` (или аналог), логин в UI, терминал.
4. e2e: `mcp_server/.venv/Scripts/python.exe .for_agent/test/e2e_mcp_stand.py`
   — ALL PASS = перенос закончен.
5. Токен переносить руками — `.env` в git не попадает (проверено игнором).
