"""Правила путей: абсолютность, границы областей, symlink."""
from __future__ import annotations

import os

import pytest

from conftest import posix_only


def test_relative_path_rejected(ctx):
    response = ctx.call("list_dir", path="ws")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "not_absolute"


def test_missing_path_rejected(ctx):
    response = ctx.call("list_dir")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_not_found(ctx):
    response = ctx.call("read_file", path=str(ctx.root / "nope.txt"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_write_outside_workspace_forbidden(ctx, tmp_path):
    outside = (tmp_path / "outside.txt").resolve()
    response = ctx.call("write_file", path=str(outside), content="x")
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "outside_workspace"
    assert "ws" in error["hint"]


def test_read_outside_workspace_allowed(ctx, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("hello\n", encoding="utf-8")
    text = ctx.text("read_file", path=str(outside))
    assert "hello" in text


@posix_only
def test_symlink_escape_forbidden(ctx, tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    link = ctx.root / "escape"
    os.symlink(outside_dir, link)

    response = ctx.call("write_file", path=str(link / "x.txt"), content="x")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "outside_workspace"


@pytest.mark.parametrize("tool", ["read_file", "list_dir", "glob", "grep"])
def test_null_byte_rejected(ctx, tool):
    payload = {"path": str(ctx.root) + "\x00x"}
    if tool in ("glob", "grep"):
        payload["pattern"] = "*"
    response = ctx.call(tool, **payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_path"
