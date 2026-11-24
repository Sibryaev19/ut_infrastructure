FROM jupyterhub/jupyterhub:5

# DockerSpawner + docker SDK для управления пользовательскими контейнерами
RUN pip install --no-cache-dir dockerspawner

COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py

CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
