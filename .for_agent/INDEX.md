# INDEX (корень ut_infrastructure)

Корень — инфраструктурный репозиторий для universal_toolkit и работы с
данными (см. README.md). Бывший funny_projects: 2026-11-28 переименован в
ut_infrastructure, pet-проекты (img_translator, jira_analyzer,
shit_downloader) убраны из репо.

## Текущее состояние (2026-11-28, чат переезда)
- ПЕРЕЕЗД: локальная часть ВЫПОЛНЕНА — папка переименована, игрушки убраны,
  пути в .env/.for_agent/README поправлены, .venv пересоздан, README
  переписан под ut_infrastructure. Решения и детали —
  [context.md](context.md).
- ХВОСТЫ ПЕРЕЕЗДА (проверить/закрыть в новом чате):
  1. GitHub rename: Sibryaev19/funny_projects → Sibryaev19/ut_infrastructure
     (web: Settings → General → Repository name, или `gh repo rename`).
  2. `git remote set-url origin git@github.com:Sibryaev19/ut_infrastructure.git`,
     push веток toolkit и main.
  3. Незакоммиченные правки .for_agent от 2026-11-28 (коммит за пользователем).
  4. Новый репозиторий funny_projects под игрушки: git init + начальный
     коммит; их старые описания для README — в истории этого репо
     (git log -- README.md).
- ДАЛЬШЕ: пользователь создаёт модули greenplum/ и hdfs/ — соседние папки
  здесь, паттерн env/setup/start, свои .for_agent. Связка со стендом
  local_datalab — через external docker-сеть ${NETWORK_NAME}.

## Файлы
- [context.md](context.md) — решения уровня репо: разделение монорепо,
  инфраструктурные соседи (gp/hdfs). Читать первым.

## Проекты
- local_datalab/, datalab_mcp/, universal_toolkit/, datalab_data_transfer/ —
  рабочие заметки агента каждого — в его .for_agent/, читать сначала её INDEX.md.

## Общие правила (для всех проектов сюда же)
- .venv внутри проекта; зависимости — requirements.txt проекта.
- Личные настройки — .env в корне проекта (шаблон .env.example); .env в .gitignore.
- Рабочие заметки агента — .for_agent/ в корне проекта, **хранятся в репозитории**
  (решение пользователя 2026-11-13: в .gitignore НЕ добавлять).
