"""list_dir: порядок, типы, symlink, обрезка."""
from __future__ import annotations

import os

from conftest import posix_only


def test_list_dir_orders_dirs_first(ctx):
    (ctx.root / "b_dir").mkdir()
    (ctx.root / "a.txt").write_text("a", encoding="utf-8")
    (ctx.root / "c.txt").write_text("c", encoding="utf-8")

    text = ctx.text("list_dir", path=str(ctx.root))
    body = [line for line in text.splitlines() if line and not line.startswith(("path=", "entries="))]
    assert body[0].startswith("d")
    assert "b_dir" in body[0]
    assert body[1].startswith("f")
    assert "a.txt" in body[1]


@posix_only
def test_list_dir_shows_symlink_target(ctx):
    target = ctx.root / "real.txt"
    target.write_text("x", encoding="utf-8")
    os.symlink(target, ctx.root / "link.txt")

    text = ctx.text("list_dir", path=str(ctx.root))
    assert "link.txt -> " in text


def test_list_dir_truncates(ctx):
    for index in range(205):
        (ctx.root / f"f{index:03d}.txt").write_text("x", encoding="utf-8")

    meta = ctx.meta("list_dir", path=str(ctx.root))
    assert meta["total_entries"] == 205
    assert meta["shown"] == 200
    assert meta["truncated"] is True


def test_list_dir_on_file_rejected(ctx):
    path = ctx.root / "a.txt"
    path.write_text("x", encoding="utf-8")
    response = ctx.call("list_dir", path=str(path))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "not_a_directory"


def test_list_dir_extra_fields_ignored(ctx):
    """Старые клиенты могут слать лишние поля (например, depth) — это не ошибка."""
    response = ctx.call("list_dir", path=str(ctx.root), depth=2)
    assert response.status_code == 200
    assert "entries=" in response.json()["text"]
