"""Минимальный парсер .env на чистом stdlib (без python-dotenv).

Формат: KEY=VALUE, по одному на строку. Поддерживается:
- пустые строки и комментарии `#` (в начале строки);
- пробелы вокруг ключа и значения;
- значение может содержать `=`;
- экранирования, кавычек и подстановок нет — значения проекта простые.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def load(path: Path = ENV_PATH) -> dict[str, str]:
    """Читает .env и возвращает словарь ключ → значение."""
    env: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def get(key: str, default: str | None = None) -> str | None:
    """Значение из .env корня проекта (или default, если ключа нет)."""
    return load().get(key, default)
