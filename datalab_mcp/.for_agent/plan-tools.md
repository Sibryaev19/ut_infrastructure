# plan-tools.md — инструменты agent_server (часть 2)

Статус: **done** — сервер реализован 2026-11-24, ждёт прогона на Ubuntu пользователя.

## Границы этапа
Реализуем **только сервер на datalab** (FastAPI). MCP-прокси на компьютере —
следующий этап; он будет вызывать эти же эндпоинты 1:1 и не добавляет логики.

## Принятые решения
| Решение | Значение | Дата |
|---|---|---|
| Имена тулов | `read_file` / `write_file` / `edit_file` / `bash` / `list_dir` / `glob` / `grep` / `workspace_info` | 11-23 |
| Пути | только POSIX-абсолютные | 11-23 |
| Чтение вне областей | не ограничивается | 11-23 |
| Запись | только внутри областей | 11-23 |
| Долгие команды | только таймаут, job-режима нет | 11-23 |
| Защита от затирания | необязательный `expected_mtime_ms` | 11-24 |
| Формат ответа | текст с шапкой; ошибки структурированы | 11-24 |
| `path` / `workdir` | обязательны, дефолтов нет | 11-24 |
| Набор v1 | 8 тулов, без delete/move/mkdir | 11-24 |
| Авторизация | на стороне datalab, в коде сервера не проверяем | 11-23 |

## Модель областей и путей
- Области задаются конфигом сервера (env), не через MCP Roots
  (Roots deprecated, SEP-2577; они никогда не были контролем доступа).
- Проверка записи: `resolve()` + `relative_to(root)` по каждому корню,
  symlink-выход запрещён.
- Граница — защита от ошибок, не песочница: `bash` пишет куда угодно.
- Каждый ответ содержит резолвнутый абсолютный путь.
- Сервер без состояния: нет «сессии» и «активного каталога»; повторы и
  параллельные вызовы безопасны.

## Контракты тулов

### workspace_info()
`{host, os, workspaces: [{name, path}], limits: {...}, path_rules}`.
Лимиты отдаём намеренно: агент сразу берёт `offset`, а не ловит ошибку.

### list_dir(path, depth=1)
Имя, тип (file/dir/symlink), размер, mtime; каталоги сверху, затем по имени;
скрытые видны и помечены; symlink показывает цель. Плоский листинг (рекурсию
закрывает `glob`), лимит 200 записей + `truncated`.

### read_file(path, offset=1, limit=2000)
Нумерация строк как `cat -n`; шапка: `total_lines`, `mtime`, `size`;
`next_offset` при обрезке.
- бинарник (NUL) → `binary_file`
- пустой файл → явный нотис «file is empty»
- каталог → `is_directory` + подсказка `list_dir`
- >64 КиБ на ответ → режем по границе строки, `truncated_by_bytes`
- строка >2000 символов → обрезка с маркером
- не-UTF8 → `errors="replace"`, флаг `encoding_lossy`

### write_file(path, content, expected_mtime_ms=None)
Атомарно: `.tmp` в том же каталоге → fsync → `os.replace`; родители создаются;
лимит 1 МиБ inline.
- **режим файла сохраняется** явным `chmod` (иначе скрипт 755 станет 644)
- `expected_mtime_ms` задан и mtime другой → `stale_file`
- «нельзя писать без предварительного read» НЕ вводим (нужно состояние)

### edit_file(path, old_string, new_string, replace_all=false, expected_mtime_ms=None)
Точное литеральное совпадение. 0 → `not_found_in_file`; >1 без `replace_all` →
`not_unique` **с номерами строк совпадений**; пустой `old_string` → ошибка.
Атомарно, режим сохраняется. Лимит файла 10 МиБ.
В `not_found_in_file` детектируем CRLF и пишем об этом.

### glob(pattern, path, limit=100)
Сортировка по mtime (свежие сверху), лимит 100, полный список — в spill-файл.
Пропускаем `.git`, `__pycache__`, `.venv`, `node_modules`, скрытые каталоги.

### grep(pattern, path, include=None, literal=false, limit=100)
Python `re`; вывод `файл:строка:текст`; 2 КиБ на строку; бинарники пропускаются;
тот же список игнорируемых каталогов; лимит на число просмотренных файлов.
Если `rg` есть в PATH — используем его (контракт не меняется).

### bash(command, description, workdir, timeout_ms=120000)
`bash -lc` (профиль → PATH, conda/venv). `stdout` и `stderr` раздельно +
`exit_code`.
- таймаут → убить группу процессов (`setsid` + `killpg`), частичный вывод,
  `timed_out: true`
- вывод >30 000 символов → полный лог в spill-файл, агенту хвост + путь
- интерактив невозможен: в описании тула `-y`/`--no-pager`; env `PAGER=cat`,
  `GIT_PAGER=cat`, `PYTHONUNBUFFERED=1`, `PYTHONIOENCODING=utf-8`
- `run_in_background` не вводим: без job-режима результат некуда забрать

## Общее
- Ответ — текст с шапкой `path=... (resolved)`; ошибка — код + сообщение + подсказка.
- Лимиты: read 2000 строк / 64 КиБ; write 1 МиБ; edit 10 МиБ; glob/grep 100;
  bash 30 000 символов, timeout 120 с (макс. 600 с); list_dir 200.

## HTTP API (согласовано 11-24)
- REST по тулу: `POST /tools/<name>` для каждого из 8 тулов,
  `GET /health`, `GET /info` (= `workspace_info`).
- Успех: `200 {"ok": true, "text": "...", "meta": {...}}` — `text` прокси отдаёт
  агенту как есть, `meta` несёт флаги обрезки.
- Ошибка: `{"error": {"code", "message", "hint"}}` + HTTP-статус:

| Код | HTTP |
|---|---|
| `bad_path`, `not_absolute`, `not_unique`, `not_found_in_file` | 400 |
| `outside_workspace` | 403 |
| `not_found`, `is_directory` | 404 |
| `stale_file` | 409 |
| `too_large` | 413 |
| `binary_file` | 415 |
| `timeout` | 504 |
| `internal` | 500 |

## Конфиг (env-only, как в datalab_data_transfer/server.py)
```
WORKSPACES="gigacode=/home/datalab/nfs/other/gigacode_test;data=/home/datalab/nfs/other/data"
PORT=9999
SPILL_DIR=/tmp/datalab_mcp
LOG_LEVEL=info
```
Реальные пути вписывает пользователь; в коде это строки.

## Layout
```
datalab_mcp/
  server/            # всё, что уезжает на datalab
    app.py           # FastAPI, роуты, обработчики ошибок
    core/            # paths, limits, errors, spill
    tools/           # fs, search, shell, info
    tests/           # pytest
    requirements.txt
    .env.example
  client/            # следующий этап: MCP stdio
  .for_agent/
```

## Проверка
Windows-машина агента не может прогнать POSIX-сервер. Пользователь коммитит и
переносит на свой Ubuntu-комп, запускает `pytest` там, ошибки присылает обратно.
Значит: код и тесты должны быть самодостаточными и не требовать моей отладки на месте.

## Чек-лист
- [x] Имена, пути, чтение, долгие команды (11-23)
- [x] Защита от затирания, формат ответа, обязательность path, набор тулов (11-24)
- [x] Контракты всех 8 тулов
- [x] Форма HTTP API, коды ошибок, конфиг, layout (11-24)
- [x] Способ проверки: pytest на Ubuntu у пользователя (11-24)
- [x] Реализация сервера
- [x] pytest-набор (на Windows: 47 passed, 12 skipped — POSIX-зависимые)
- [ ] Прогон на Ubuntu пользователя

## Отклонения и заметки
- `bash` по таймауту возвращает **200** с `timed_out: true` и частичным выводом,
  а не 504: агенту нужен хвост вывода, а 504 его потеряет. Код `timeout` в
  таблице остался неиспользованным.
- Добавлены коды сверх плана: `not_a_directory` (400), `encoding_error` (400).
- Windows-прогон не покрывает: `bash`, сохранение mode-битов, symlink-выход —
  это ровно те места, где возможны сюрпризы на Ubuntu.

## Не входит в v1
`apply_patch`, `move/copy/delete`, `upload/download`, git-тулы, MCP resources,
job-режим, streaming вывода.
