"""Общие фикстуры для тестов сервера.

Тесты запускаются из каталога server/ (см. pytest.ini).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import create_app
from core.config import Config, Workspace

posix_only = pytest.mark.skipif(
    os.name != "posix", reason="требует POSIX (Linux): bash, mode bits, symlink"
)


@dataclass
class Ctx:
    root: Path
    client: TestClient
    config: Config

    def call(self, tool: str, **payload):
        return self.client.post(f"/tools/{tool}", json=payload)

    def text(self, tool: str, **payload) -> str:
        response = self.call(tool, **payload)
        assert response.status_code == 200, response.text
        return response.json()["text"]

    def meta(self, tool: str, **payload) -> dict:
        response = self.call(tool, **payload)
        assert response.status_code == 200, response.text
        return response.json()["meta"]


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    root = (tmp_path / "ws").resolve()
    root.mkdir()
    config = Config(
        workspaces=(Workspace(name="ws", path=root),),
        spill_dir=(tmp_path / "spill").resolve(),
        log_level="info",
    )
    return Ctx(root=root, client=TestClient(create_app(config)), config=config)
