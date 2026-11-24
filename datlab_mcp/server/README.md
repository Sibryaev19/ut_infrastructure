# agent_server — инструменты агента на datalab

FastAPI-сервер, который даёт локальному агенту (MCP-прокси на компьютере)
файловые и shell-инструменты в проектных областях на datalab.

Сервер **без состояния**: нет «сессии», нет «активного каталога».
Авторизация — на стороне платформы (jupyterhub); токен здесь не проверяется.

Требуется Python ≥ 3.10 (используются `str | None` и `Path.is_relative_to`-подобная логика).

## Запуск

```bash
pip install -r requirements.txt

WORKSPACES="gigacode=/home/datalab/nfs/other/gigacode_test" \
SPILL_DIR=/tmp/datalab_mcp \
PORT=9999 \
python app.py
```

Или через uvicorn:

```bash
WORKSPACES=... uvicorn app:build_default_app --factory --host 0.0.0.0 --port 9999
```

`WORKSPACES` — список областей через `;`, формат `имя=/абсолютный/путь`.
Имя нужно только для отображения и понятных ошибок.

## Эндпоинты

| Метод | Путь | Аргументы |
|---|---|---|
| GET | `/health` | — |
| GET | `/info` | — |
| POST | `/tools/workspace_info` | — |
| POST | `/tools/list_dir` | `path`, `depth=1` |
| POST | `/tools/read_file` | `path`, `offset=1`, `limit=2000` |
| POST | `/tools/write_file` | `path`, `content`, `expected_mtime_ms?` |
| POST | `/tools/edit_file` | `path`, `old_string`, `new_string`, `replace_all=false`, `expected_mtime_ms?` |
| POST | `/tools/glob` | `pattern`, `path`, `limit=100` |
| POST | `/tools/grep` | `pattern`, `path`, `include?`, `literal=false`, `limit=100` |
| POST | `/tools/bash` | `command`, `workdir`, `timeout_ms=120000`, `description?` |

Ответ:

```json
{"ok": true, "text": "path=/abs/file\n...", "meta": {"...": "..."}}
```

Ошибка: HTTP-статус + `{"error": {"code", "message", "hint"}}`.

```bash
curl -s localhost:9999/tools/read_file \
  -H 'content-type: application/json' \
  -d '{"path": "/home/datalab/nfs/other/gigacode_test/app.py", "limit": 20}'
```

## Правила путей

- Принимаются только абсолютные POSIX-пути. Относительные — ошибка `not_absolute`.
- Чтение не ограничено областями.
- Запись (`write_file`, `edit_file`) — только внутри `WORKSPACES`.
- Путь разрешается (`resolve()`), поэтому symlink за пределы области считается
  выходом за пределы области.
- Граница — защита от случайной ошибки, а не песочница: `bash` пишет куда угодно.

## Поведение, о котором стоит знать

- `read_file` нумерует строки (`cat -n`). Для `edit_file` префикс нужно срезать.
- `write_file`/`edit_file` пишут атомарно и **сохраняют права файла** (755 не станет 644).
- `expected_mtime_ms` — защита от перезаписи устаревшего файла; при расхождении `stale_file`.
- `edit_file` требует единственного совпадения `old_string`; иначе `not_unique`
  с номерами строк. Если файл в CRLF, а `old_string` с `\n` — подсказка об этом.
- `glob`/`grep` не заходят в `.git`, `__pycache__`, `.venv`, `node_modules` и скрытые каталоги.
- `glob` без `/` в шаблоне ищет только в корне (`*.md`), рекурсивно — `**/*.md`.
- `bash` — свежая оболочка на вызов, `bash -lc` (профиль загружается), `cd` не сохраняется.
- `bash` по таймауту убивает группу процессов и возвращает **200** с `timed_out: true`
  и частичным выводом: агенту нужен этот хвост, а потерять его из-за 504 было бы хуже.
- Вывод больше 30 000 символов уезжает в spill-файл (`SPILL_DIR`); агенту — хвост и путь.

## Тесты

```bash
python -m pytest
```

На Windows прогоняются все тесты, кроме POSIX-зависимых (`bash`, сохранение прав,
symlink) — они помечены `posix_only` и пропускаются.
