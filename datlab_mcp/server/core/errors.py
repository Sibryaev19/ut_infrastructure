"""Ошибки инструментов и их отображение в HTTP-статусы."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Код ошибки -> HTTP-статус. Таблица зафиксирована в плане (.for_agent/plan-tools.md).
STATUS_BY_CODE: dict[str, int] = {
    "bad_request": 400,
    "bad_path": 400,
    "not_absolute": 400,
    "not_a_directory": 400,
    "not_unique": 400,
    "not_found_in_file": 400,
    "encoding_error": 400,
    "outside_workspace": 403,
    "not_found": 404,
    "is_directory": 404,
    "stale_file": 409,
    "too_large": 413,
    "binary_file": 415,
    "timeout": 504,
    "internal": 500,
}


@dataclass
class ToolError(Exception):
    """Ошибка, которую агент должен понять и исправить.

    message — что случилось, hint — что делать дальше.
    """

    code: str
    message: str
    hint: str | None = None
    status: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status is None:
            self.status = STATUS_BY_CODE.get(self.code, 500)
        Exception.__init__(self, self.message)

    def to_body(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            error["hint"] = self.hint
        error.update(self.extra)
        return {"error": error}
