"""Настройки: обязательные поля, разбор булевых и числовых значений."""
from __future__ import annotations

import pytest

from src.config import ConfigError, load_settings


def test_loads_required_values():
    settings = load_settings(
        {"DATALAB_URL": "https://datalab.test/9999/", "DATALAB_TOKEN": "tok"}
    )
    assert settings.datalab_url == "https://datalab.test/9999"
    assert settings.datalab_token == "tok"
    assert settings.verify_tls is False


def test_missing_url():
    with pytest.raises(ConfigError, match="DATALAB_URL"):
        load_settings({"DATALAB_TOKEN": "tok"})


def test_missing_token():
    with pytest.raises(ConfigError, match="DATALAB_TOKEN"):
        load_settings({"DATALAB_URL": "https://x/1"})


def test_bad_scheme():
    with pytest.raises(ConfigError, match="http"):
        load_settings({"DATALAB_URL": "datalab.test:9999", "DATALAB_TOKEN": "t"})


@pytest.mark.parametrize("raw, expected", [
    ("true", True),
    ("1", True),
    ("yes", True),
    ("false", False),
    ("0", False),
    ("", False),
])
def test_verify_tls_parsing(raw, expected):
    settings = load_settings(
        {"DATALAB_URL": "https://x/1", "DATALAB_TOKEN": "t", "VERIFY_TLS": raw}
    )
    assert settings.verify_tls is expected


def test_custom_timeout():
    settings = load_settings(
        {"DATALAB_URL": "https://x/1", "DATALAB_TOKEN": "t", "HTTP_TIMEOUT": "45"}
    )
    assert settings.timeout == 45.0


def test_bad_timeout():
    with pytest.raises(ConfigError, match="HTTP_TIMEOUT"):
        load_settings(
            {"DATALAB_URL": "https://x/1", "DATALAB_TOKEN": "t", "HTTP_TIMEOUT": "soon"}
        )
