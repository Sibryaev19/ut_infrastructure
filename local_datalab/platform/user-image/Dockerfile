# Образ пользователя datalab: notebook + зависимости server/ из datalab_mcp.
# За основу — стек jupyter (внутри есть jupyterhub-singleuser, нужный DockerSpawner).
FROM quay.io/jupyter/minimal-notebook:python-3.12.10

# Зависимости server/ (версии — как в datalab_mcp/server/requirements.txt)
RUN pip install --no-cache-dir \
    fastapi==0.165.0 \
    uvicorn==0.54.0 \
    anyio==4.16.0 \
    pydantic==2.14.4 \
    httpx==0.28.1 \
    jupyter-server-proxy

# Папка workspace, как на datalab (содержимое приедет через mount)
USER root
RUN mkdir -p /home/datalab/nfs && chown ${NB_UID}:${NB_GID} /home/datalab/nfs
USER ${NB_UID}
