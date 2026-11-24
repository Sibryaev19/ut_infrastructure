"""Ошибки клиента datalab в том виде, в котором их прочитает агент.

Формат совпадает с серверным конвертом:
    error=<code>
    message=<что случилось>
    hint=<что делать>
"""
from __future__ import annotations


class DatalabError(Exception):
    """Сервер datalab ответил ошибкой (4xx/5xx)."""

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status = status

    def __str__(self) -> str:
        lines = [f"error={self.code}", f"message={self.message}"]
        if self.hint:
            lines.append(f"hint={self.hint}")
        return "\n".join(lines)


class DatalabTransportError(Exception):
    """До datalab не достучались: сеть, TLS, таймаут."""

    def __init__(self, kind: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        lines = [f"error={self.kind}", f"message={self.message}"]
        if self.hint:
            lines.append(f"hint={self.hint}")
        return "\n".join(lines)
