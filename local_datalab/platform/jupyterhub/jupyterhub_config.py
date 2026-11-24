"""Конфиг jupyterhub: имитация datalab на локальном Docker.

HOST_BASE_DIR и NETWORK_NAME приходят через environment из compose
(в конечном счёте — из .env в корне проекта).
"""

import os

_base_host = os.environ["HOST_BASE_DIR"]
_network_name = os.environ["NETWORK_NAME"]

# --- Сеть и порт -----------------------------------------------------------
# Внутренний порт всегда 8000; наружу выставляется HUB_PORT в compose
c.JupyterHub.bind_url = "http://0.0.0.0:8000"
c.JupyterHub.ip = "0.0.0.0"

# Hub доступен пользовательским контейнерам по имени сервиса в compose-сети
c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.hub_connect_ip = "jupyterhub"

# --- Авторизация: имитацию не делаем, логинится кто угодно -----------------
from jupyterhub.auth import DummyAuthenticator  # noqa: E402

c.JupyterHub.authenticator_class = DummyAuthenticator
c.DummyAuthenticator.allow_all = True
c.Authenticator.allowed_users = set()

# --- Спавн: как datalab поднимает контейнер на пользователя ----------------
from dockerspawner import DockerSpawner  # noqa: E402

c.JupyterHub.spawner_class = DockerSpawner
c.DockerSpawner.image = "local_datalab-user:latest"

# та же compose-сеть, где живёт hub
c.DockerSpawner.network_name = _network_name

# workspace: путь /home/datalab/nfs как на datalab.
# Источник — АБСОЛЮТНЫЙ путь на хосте: dockerspawner передаёт его напрямую
# демону хоста (пути изнутри контейнера hub демону не видны).
_workspace_host = f"{_base_host}/workspace"

# Персональный home пользователя переживает рестарты контейнера
# (notebook'и из /home/jovyan/work, pip --user, настройки jupyterlab).
# uid/gid хоста и контейнера совпадают (1000) — права ок.
c.DockerSpawner.volumes = {
    _workspace_host: "/home/datalab/nfs",
    f"{_base_host}/persistent/jupyter-{{username}}": "/home/jovyan",
}


async def _ensure_home(spawner):
    """Создаём домашнюю папку пользователя на хосте до старта контейнера.

    Hub работает от root, поэтому свежая папка получает root-владельца —
    сразу отдаём её uid/gid пользователя контейнера (NB_UID=1000, NB_GID=100).
    """
    import os

    path = f"{_base_host}/persistent/jupyter-{spawner.user.name}"
    os.makedirs(path, exist_ok=True)
    # work/ из образа скрыт маунтом — создаём его на хосте
    work = f"{path}/work"
    os.makedirs(work, exist_ok=True)
    os.chown(path, 1000, 100)
    os.chown(work, 1000, 100)


c.Spawner.pre_spawn_hook = _ensure_home
c.DockerSpawner.environment = {
    "WORKSPACES": "/home/datalab/nfs",
}

# стартовая папка notebook'а — workspace, как на datalab
c.DockerSpawner.notebook_dir = "/home/datalab/nfs"
# рабочая директория процесса сервера: терминалы стартуют из неё же
# (root_dir управляет только файловым браузером, не терминалом).
# У DockerSpawner нет trait'а working_dir — задаём через параметры
# docker create (у hub-образа WORKDIR=/home/jovyan).
c.DockerSpawner.extra_create_kwargs = {"working_dir": "/home/datalab/nfs"}
c.Spawner.args = ["--ServerApp.root_dir=/home/datalab/nfs"]

# чтобы контейнеры пользователей не копились после остановки
c.DockerSpawner.remove = True

# таймауты щедрые — первый старт может тянуть ничего, но hub ждёт старта ядра
c.Spawner.start_timeout = 120
c.Spawner.http_timeout = 60
