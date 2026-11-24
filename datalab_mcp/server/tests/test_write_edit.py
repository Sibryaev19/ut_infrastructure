"""write_file и edit_file: атомарность, режим, stale, уникальность."""
from __future__ import annotations

import os
import stat

from conftest import posix_only


def test_write_creates_file(ctx):
    path = ctx.root / "sub" / "new.txt"
    meta = ctx.meta("write_file", path=str(path), content="hello\n")
    assert meta["created"] is True
    assert meta["bytes"] == 6
    assert path.read_text(encoding="utf-8") == "hello\n"


def test_write_overwrites(ctx):
    path = ctx.root / "a.txt"
    path.write_text("old\n", encoding="utf-8")
    meta = ctx.meta("write_file", path=str(path), content="new\n")
    assert meta["created"] is False
    assert path.read_text(encoding="utf-8") == "new\n"


@posix_only
def test_write_preserves_mode(ctx):
    path = ctx.root / "run.sh"
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(path, 0o755)

    ctx.call("write_file", path=str(path), content="#!/bin/sh\necho hi\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o755


def test_write_stale_mtime(ctx):
    path = ctx.root / "a.txt"
    path.write_text("one\n", encoding="utf-8")
    old_mtime = int(round(path.stat().st_mtime * 1000))

    # файл изменился после того, как агент его прочитал
    path.write_text("two\n", encoding="utf-8")
    os.utime(path, (0, 0))

    response = ctx.call(
        "write_file", path=str(path), content="three\n", expected_mtime_ms=old_mtime
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_file"


def test_write_expected_mtime_for_missing_file(ctx):
    response = ctx.call(
        "write_file",
        path=str(ctx.root / "missing.txt"),
        content="x",
        expected_mtime_ms=123,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_file"


def test_write_too_large(ctx):
    response = ctx.call("write_file", path=str(ctx.root / "big.txt"), content="x" * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_large"


def test_edit_unique(ctx):
    path = ctx.root / "a.py"
    path.write_text("value = 1\n", encoding="utf-8")
    meta = ctx.meta(
        "edit_file", path=str(path), old_string="value = 1", new_string="value = 2"
    )
    assert meta["replaced"] == 1
    assert path.read_text(encoding="utf-8") == "value = 2\n"


def test_edit_not_unique(ctx):
    path = ctx.root / "a.py"
    path.write_text("x = 1\nx = 1\n", encoding="utf-8")
    response = ctx.call(
        "edit_file", path=str(path), old_string="x = 1", new_string="x = 2"
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "not_unique"
    assert error["lines"] == [1, 2]


def test_edit_replace_all(ctx):
    path = ctx.root / "a.py"
    path.write_text("x = 1\nx = 1\n", encoding="utf-8")
    meta = ctx.meta(
        "edit_file",
        path=str(path),
        old_string="x = 1",
        new_string="x = 2",
        replace_all=True,
    )
    assert meta["replaced"] == 2
    assert path.read_text(encoding="utf-8") == "x = 2\nx = 2\n"


def test_edit_not_found(ctx):
    path = ctx.root / "a.py"
    path.write_text("value = 1\n", encoding="utf-8")
    response = ctx.call(
        "edit_file", path=str(path), old_string="nope", new_string="x"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "not_found_in_file"


def test_edit_crlf_hint(ctx):
    path = ctx.root / "win.txt"
    path.write_bytes(b"one\r\ntwo\r\n")
    response = ctx.call(
        "edit_file", path=str(path), old_string="one\ntwo", new_string="x"
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "not_found_in_file"
    assert "CRLF" in error["hint"]


def test_edit_identical_strings(ctx):
    path = ctx.root / "a.py"
    path.write_text("x = 1\n", encoding="utf-8")
    response = ctx.call(
        "edit_file", path=str(path), old_string="x = 1", new_string="x = 1"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_edit_empty_old_string(ctx):
    path = ctx.root / "a.py"
    path.write_text("x = 1\n", encoding="utf-8")
    response = ctx.call("edit_file", path=str(path), old_string="", new_string="y")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"
