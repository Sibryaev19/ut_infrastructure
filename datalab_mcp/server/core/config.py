"""Конфигурация сервера: проектные области и служебные каталоги.

Читается из окружения (как server.py в datalab_data_transfer: на datalab .env
не используется). Формат WORKSPACES:

    WORKSPACES="gigacode=/home/datalab/nfs/other/gigacode_test;data=/home/datalab/data"

Имя области нужно только для отображения и для понятных ошибок.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_SPILL_DIR = "/tmp/datalab_mcp"


@dataclass(frozen=True)
class Workspace:
    name: str
    path: Path


@dataclass(frozen=True)
class Config:
    workspaces: tuple[Workspace, ...]
    spill_dir: Path
    log_level: str = "info"

    def workspace_names(self) -> str:
        return ", ".join(f"{w.name}={w.path}" for w in self.workspaces)


def parse_workspaces(raw: str) -> tuple[Workspace, ...]:
    workspaces: list[Workspace] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, sep, path = chunk.partition("=")
        if not sep:
            raise ValueError(
                f"WORKSPACES: ожидается 'name=/abs/path', получено {chunk!r}"
            )
        name = name.strip()
        if not name:
            raise ValueError(f"WORKSPACES: пустое имя области в {chunk!r}")
        candidate = Path(path.strip()).expanduser()
        if not candidate.is_absolute():
            raise ValueError(
                f"WORKSPACES: путь области {name!r} должен быть абсолютным: {candidate}"
            )
        workspaces.append(Workspace(name=name, path=candidate.resolve()))
    if not workspaces:
        raise ValueError("WORKSPACES: не задано ни одной проектной области")
    return tuple(workspaces)


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    return Config(
        workspaces=parse_workspaces(env.get("WORKSPACES", "")),
        spill_dir=Path(env.get("SPILL_DIR", DEFAULT_SPILL_DIR)).expanduser(),
        log_level=env.get("LOG_LEVEL", "info").lower(),
    )
