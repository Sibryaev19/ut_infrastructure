# datalab MCP server (часть 1)

stdio-MCP-сервер для агента: восемь тонких инструментов, каждый — один HTTP-вызов
к серверу на datalab (`../server/`). Своей логики путей здесь нет: всё решает
удалённый сервер, здесь только транспорт и перевод ошибок.

```
агент --stdio--> main.py --HTTPS--> datalab: /tools/<name>
```

## Установка

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # и вписать DATALAB_URL / DATALAB_TOKEN
```

## Подключение к агенту

Процесс поднимает сам клиент агента — запускать и убивать сервер руками не нужно.
Фрагмент конфига (формат ключей зависит от клиента; для большинства — так):

```json
{
  "mcpServers": {
    "datalab": {
      "command": "/abs/path/datlab_mcp/mcp_server/.venv/bin/python",
      "args": ["/abs/path/datlab_mcp/mcp_server/main.py"],
      "env": {
        "DATALAB_URL": "https://<datalab-host>/<port>",
        "DATALAB_TOKEN": "<JUPYTERHUB_API_TOKEN>",
        "VERIFY_TLS": "false"
      }
    }
  }
}
```

На Windows путь к интерпретатору — `.venv\Scripts\python.exe`.
Если клиент не передаёт `env`, настройки берутся из `.env` рядом с `main.py`.

## Инструменты

| Тул | Параметры | Что делает |
|---|---|---|
| `workspace_info` | — | проектные области (корни записи), хост, лимиты |
| `list_dir` | `path`, `depth=1` | содержимое каталога |
| `read_file` | `path`, `offset=1`, `limit=2000` | текст с нумерацией строк |
| `write_file` | `path`, `content`, `expected_mtime_ms?` | атомарная запись в области |
| `edit_file` | `path`, `old_string`, `new_string`, `replace_all=false`, `expected_mtime_ms?` | точная замена |
| `glob` | `pattern`, `path`, `limit=100` | поиск файлов по шаблону |
| `grep` | `pattern`, `path`, `include?`, `literal=false`, `limit=100` | поиск по содержимому |
| `bash` | `command`, `workdir`, `timeout_ms=120000`, `description?` | команда на datalab |

## Поведение

- Все пути — абсолютные POSIX на удалённой машине. Локальные пути не работают.
- Ошибки datalab приходят агенту как результат с `isError` и текстом
  `error=... / message=... / hint=...` — агент может исправить вызов сам.
- `bash` ждёт на 30 с дольше, чем таймаут команды на сервере, чтобы не оборвать её.
- Логи — только в stderr: stdout занят протоколом MCP.
- Ретраев нет: `write_file`/`edit_file` не идемпотентны.

## Тесты

```bash
python -m pytest
```

Тесты не ходят в настоящий datalab: `httpx.MockTransport` подменяет сервер.
`tests/test_contract.py` сверяет схемы тулов с сигнатурами обработчиков,
чтобы объявления и реализация не разъехались.
