# context.md — корень ut_infrastructure

## Суть репо
Инфраструктурный репозиторий для universal_toolkit и работы с данными
(не только datalab). Бывший funny_projects: pet-проекты вынесены, набор
развивается как экосистема кирпичей. Описание частей — README.md.

## Разделение монорепо (решено + локально выполнено 2026-11-28)
- Набор (local_datalab, datalab_mcp, universal_toolkit, datalab_data_transfer,
  будущие gp/hdfs и далее — не только datalab) выделен ПЕРЕИМЕНОВАНИЕМ
  монорепо funny_projects → ut_infrastructure; история сохранена целиком,
  без filter-repo. Выполнено: папка переименована, игрушки убраны, пути в
  .env/.for_agent/README поправлены, .venv local_datalab пересоздан.
- img_translator, jira_analyzer, shit_downloader — в новый отдельный
  репозиторий funny_projects (свежий git init, история игрушек не
  переносится); их старые описания для README — в истории этого репо
  (git log -- README.md).
- GitHub: Sibryaev19/funny_projects → Sibryaev19/ut_infrastructure; имя
  funny_projects освобождается. Старый URL redirect'ит.

## Инфраструктурные соседи (решено 2026-11-28)
- Greenplum и HDFS — часть имитации datalab, но живут ОТДЕЛЬНЫМИ модулями —
  соседними папками здесь (НЕ внутри local_datalab), паттерн env/setup/start,
  у каждого своя .for_agent. Пользователь поднимает их руками; стенд работает
  и без них.
- Связка: compose модулей дополнительно подключает сервисы к docker-сети
  ${NETWORK_NAME} (переменная из local_datalab/.env, сейчас
  local_datalab_datalab) как external — контейнеры пользователей ходят к ним
  по именам сервисов. Порты наружу не публикуются.
- Данные модулей — в их data/ (gitignored), bind-маунты. UID образов
  (postgres/hadoop) потребует chown при первом подъёме — ритуал setup'а.
- В git модули идут: трекается только код/конфиги; data/, .env, .venv — в
  их .gitignore. Секреты — в .env, в compose.yaml только ${VAR}.
