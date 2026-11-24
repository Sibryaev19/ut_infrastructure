# INDEX — local_datalab

Локальный стенд: полноценный jupyterhub в Docker, имитирующий datalab —
для тестирования `datlab_mcp` (server/ + mcp_server/) без реального datalab.

## Текущее состояние
- Шаг 1 (понимание) — завершён: цель и границы имитации согласованы, см. context.md.
- Шаг 2 (план) — не начат.
- СМЕНА ПЛАНА (2026-11-24, ночь): WSL на ноутбуке не вылечили (restorehealth +
  повторные enable-feature + `wsl --install --no-distribution` не помогли).
  Решено переносить стенд на домашний комп: Ubuntu + нативный Docker (WSL не нужен).
  Стенд будет жить на компе; mcp_server с ноута ходит по сети `http://<ip-компа>:8000`
  (VERIFY_TLS=false уже решено). Первым делом на Ubuntu проверить:
  `docker run --rm hello-world` + `docker compose version`.
  Код стенда (Шаг 2) пишем в этом проекте как обычно — он ОС-независим.
  История мучений с WSL — в [wsl-install.md](wsl-install.md).

## Связанный проект
- `C:\Users\User\Desktop\секундная\funny_projects\datlab_mcp` — тестируемый код
  (server/ и mcp_server/). Своя `.for_agent` там.

## Файлы
- [context.md](context.md) — цель, границы имитации, решения шага 1. Читать первым.

## Правила работы
- Системные действия на Ubuntu-компе (установка docker и т.п.) выполняет
  пользователь, агент готовит команды.
- Коммиты делает пользователь.
