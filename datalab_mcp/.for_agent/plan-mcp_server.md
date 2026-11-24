# plan-mcp_server.md — MCP-сервер для агента (часть 1)

Статус: **done** — реализовано и проверено end-to-end 2026-11-24.

## Задача
stdio-MCP-сервер на машине агента: 8 тулов, каждый = HTTP-вызов
`POST /tools/<name>` к уже готовому серверу на datalab. Никакой логики путей —
только транспорт и перевод ошибок.

## Принятые решения
| Решение | Значение |
|---|---|
| Папка | `mcp_server/` |
| SDK | официальный `mcp==2.3.0` (в 2.x сервер = `MCPServer`, не `FastMCP`) |
| Объявления тулов | один файл на все 8 |
| Обработчики | отдельная папка (логика вызова datalab) |
| Клиент datalab | отдельный переиспользуемый модуль-класс (как `datalab_data_transfer/client.py`, но async) |
| Ошибки агенту | `isError: true` + текст `error=/message=/hint=` |
| Instructions | статический текст; области агент получает из `workspace_info` |
| Запуск | stdio; агент поднимает процесс по конфигу, пользователь сервер не трогает |

## Структура
```
mcp_server/
  main.py                 # create mcp, register tools, run(stdio)
  src/
    config.py             # .env -> Settings: DATALAB_URL, DATALAB_TOKEN,
                          #   VERIFY_TLS, TIMEOUT, CONNECT_TIMEOUT
    datalab/
      __init__.py         # экспорт DatalabClient, DatalabError
      client.py           # класс: call(tool, payload), info(), health()
      errors.py           # DatalabError / DatalabTransportError, формат для агента
    tools/
      __init__.py
      registration.py     # register_tools(mcp, handlers): 8 @mcp.tool + схемы
    handlers/
      __init__.py         # 8 async-функций: read_file, write_file, ... bash
  tests/
    conftest.py           # httpx.MockTransport с каноническими ответами datalab
    test_client.py        # URL, заголовок token, таймауты, pass-through text/meta
    test_errors.py        # 403/404/409/413/415/504/сеть/таймаут
    test_contract.py      # параметры @mcp.tool == параметры handler (inspect)
    test_config.py        # .env, обязательные поля
  requirements.txt
  .env.example
  README.md               # + фрагмент конфига агента
```

## Слои
- **main.py** — только сборка: Settings → DatalabClient → MCPServer(instructions=) →
  register_tools → run(). Логирование в stderr (stdout занят протоколом).
- **src/datalab/client.py** — переиспользуемый, без импортов MCP. Async httpx,
  один `AsyncClient` на процесс. `call()` возвращает `(text, meta)` из ответа
  datalab; ошибки — исключениями. Ретраев нет: запись не идемпотентна.
- **src/handlers/** — тонкие функции: собрать payload, вызвать `client.call`,
  вернуть `text`. Ошибки пробрасывают наверх.
- **src/tools/registration.py** — объявления с описаниями (в них — правила
  абсолютных путей) + общий декоратор, превращающий `DatalabError` в `isError`.

## Что переиспользуем из datalab_data_transfer/client.py
- `Authorization: token <token>` и `VERIFY_TLS` (строкой из env, по умолчанию false).
- Разбор ошибки datalab: `{"detail": ...}` / `{"error": ...}` → код, сообщение, hint.
- Общую схему «тонкий слой поверх httpx», без дублирования транспорта.

## Таймауты
- connect 10 с, базовый 120 с.
- `bash` — `timeout_ms/1000 + 30` с, чтобы клиент не оборвал команду раньше сервера.

## Тесты
Полностью кросс-платформенные (MockTransport), прогоняются на Windows локально;
настоящий datalab для тестов не нужен.

## Чек-лист
- [x] Согласовать структуру
- [x] Проверить API `mcp==2.3.0` по установленному пакету
- [x] config + DatalabClient + errors
- [x] handlers + registration
- [x] main.py, README с конфигом агента
- [x] pytest (34 passed)
- [x] End-to-end через stdio с настоящим сервером (локально, порт 9998)
- [ ] Прогон на машине пользователя с реальным datalab

## Что выяснилось на реальном SDK
- В 2.x сервер — `MCPServer`, инструменты как прежде через `@mcp.tool()`;
  `ToolError` лежит в `mcp.server.mcpserver.exceptions` (не в `mcp.server`).
- `ToolError` доходит до модели как `isError=True`, но SDK добавляет префикс
  `Error executing tool <name>: `. Наш текст идёт следом — это нормально.
- `Client.list_tools()` возвращает `ListToolsResult`; список тулов — `.tools`.
- `structured_output=False` обязателен, иначе SDK пытается строить
  структурированный вывод из `-> str`.

## Проверка end-to-end (2026-11-24)
Локально поднимался `server/app.py` (порт 9998, WORKSPACES = временный каталог),
MCP-сервер запускался агентом по stdio. Проверено: список 8 тулов, `workspace_info`,
`read_file`, `write_file`, отказ записи вне области (`isError` с hint), `bash`.

## Не входит
Кэширование, ретраи, стриминг вывода, resources/prompts, upload/download.
