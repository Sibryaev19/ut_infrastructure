# context.md — local_datalab

## Цель
Одноразово собрать и переиспользовать локальный «мини-datalab»: jupyterhub
с UI в Docker, который проксирует пути в пользовательский контейнер, где
работают notebook (классика) и `server/` из datlab_mcp. Стенд для отработки
POSIX-тестов, развёртывания server/ и сквозных проверок mcp_server.

## Архитектура (черновик, согласована на шаге 1)
```
Windows: mcp_server → http://localhost:8000
   └─ compose: jupyterhub (UI, прокси)
        └─ DockerSpawner (через /var/run/docker.sock) → контейнер пользователя
             ├─ jupyter notebook
             ├─ server/ (FastAPI, WORKSPACES=/home/datalab/nfs/<name>)
             └─ volume: ./workspace ↔ /home/datalab/nfs (виден из проводника Windows)
```

## Границы имитации (решено пользователем, 2026-11-24)
- Авторизацию и проверку токена НЕ имитируем — на функционал не влияет.
  Вручную логинимся через UI (DummyAuthenticator/allow_all); bearer-токен
  при необходимости добавим позже.
- Образ пользователя — простой python:3.12 + jupyter + зависимости server/.
  Spark, kinit, fsspec и прочие детали datalab НЕ имитируем; при желании
  образ можно позже подменить на приближённый к datalab — конфиг спавнера
  не меняется.
- TLS не нужен: локально HTTP; datlab_mcp работает с VERIFY_TLS=false.
- Путь workspace в контейнере — /home/datalab/nfs/... как на datalab.

## Окружение стенда
- ХОСТ — отдельный комп с Ubuntu (нативный Docker; Windows-ноутбук отброшен
  после неудачных попыток поставить WSL/Docker — история в wsl-install.md).
- Стенд живёт на компе; mcp_server с ноутбука ходит по сети
  `http://<ip-компа>:8000` (VERIFY_TLS=false).
- Первый шаг на Ubuntu: `docker run --rm hello-world` + `docker compose version`.
- jupyterhub-контейнеру пробрасывается docker-сокет хоста
  (`/var/run/docker.sock`) — на нативном Linux это работает без нюансов.

## Стек стенда (предварительно)
- Официальный образ `jupyterhub/jupyterhub`; DockerSpawner.
- docker-compose рядом с проектом.
