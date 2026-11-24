"""read_file: страницы, нумерация, краевые случаи."""
from __future__ import annotations


def test_read_numbers_lines(ctx):
    path = ctx.root / "a.txt"
    path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    payload = ctx.meta("read_file", path=str(path))
    assert payload["total_lines"] == 3
    assert payload["returned"] == 3
    assert payload["next_offset"] is None

    text = ctx.text("read_file", path=str(path))
    assert "     1\talpha" in text
    assert "     3\tgamma" in text


def test_read_offset_and_limit(ctx):
    path = ctx.root / "a.txt"
    path.write_text("1\n2\n3\n4\n5\n", encoding="utf-8")

    meta = ctx.meta("read_file", path=str(path), offset=2, limit=2)
    assert meta["returned"] == 2
    assert meta["next_offset"] == 4
    assert meta["total_lines"] == 5

    text = ctx.text("read_file", path=str(path), offset=2, limit=2)
    assert "2\t2" in text
    assert "3\t3" in text
    assert "\t4" not in text


def test_read_empty_file(ctx):
    path = ctx.root / "empty.txt"
    path.write_text("", encoding="utf-8")
    text = ctx.text("read_file", path=str(path))
    assert "file is empty" in text


def test_read_offset_beyond_end(ctx):
    path = ctx.root / "short.txt"
    path.write_text("only\n", encoding="utf-8")
    text = ctx.text("read_file", path=str(path), offset=10)
    assert "no lines at offset 10" in text


def test_read_binary_rejected(ctx):
    path = ctx.root / "bin.dat"
    path.write_bytes(b"abc\x00def")
    response = ctx.call("read_file", path=str(path))
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "binary_file"


def test_read_directory_rejected(ctx):
    response = ctx.call("read_file", path=str(ctx.root))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "is_directory"


def test_read_long_line_truncated(ctx):
    path = ctx.root / "long.txt"
    path.write_text("x" * 3000 + "\n", encoding="utf-8")
    text = ctx.text("read_file", path=str(path))
    assert "truncated 1000 chars" in text


def test_read_marks_lossy_decoding(ctx):
    path = ctx.root / "bad.txt"
    path.write_bytes(b"\xff\xfe hello\n")
    meta = ctx.meta("read_file", path=str(path))
    assert meta["encoding_lossy"] is True


def test_read_marks_crlf(ctx):
    path = ctx.root / "crlf.txt"
    path.write_bytes(b"one\r\ntwo\r\n")
    meta = ctx.meta("read_file", path=str(path))
    assert meta["crlf"] is True
    text = ctx.text("read_file", path=str(path))
    assert "one" in text
    assert "one\r" not in text
