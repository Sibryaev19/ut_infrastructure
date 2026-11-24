"""Spill-файлы: полный вывод, когда он не влезает в ответ агенту."""
from __future__ import annotations

import uuid
from pathlib import Path

from core.config import Config


def new_spill_path(config: Config, tool: str) -> Path:
    config.spill_dir.mkdir(parents=True, exist_ok=True)
    return config.spill_dir / f"{tool}-{uuid.uuid4().hex[:12]}.log"


def write_spill(config: Config, tool: str, data: str | bytes) -> Path:
    path = new_spill_path(config, tool)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return path
