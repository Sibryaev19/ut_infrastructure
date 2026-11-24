"""glob и grep: шаблоны, игнорируемые каталоги, лимиты."""
from __future__ import annotations


def _tree(ctx):
    (ctx.root / "src" / "pkg").mkdir(parents=True)
    (ctx.root / "src" / "app.py").write_text("import os\n", encoding="utf-8")
    (ctx.root / "src" / "pkg" / "mod.py").write_text("VALUE = 42\n", encoding="utf-8")
    (ctx.root / "README.md").write_text("# docs\n", encoding="utf-8")

    ignored = ctx.root / ".git"
    ignored.mkdir()
    (ignored / "hidden.py").write_text("VALUE = 42\n", encoding="utf-8")

    cache = ctx.root / "__pycache__"
    cache.mkdir()
    (cache / "junk.py").write_text("VALUE = 42\n", encoding="utf-8")


def test_glob_recursive(ctx):
    _tree(ctx)
    text = ctx.text("glob", pattern="**/*.py", path=str(ctx.root))
    assert "app.py" in text
    assert "mod.py" in text
    assert "hidden.py" not in text
    assert "junk.py" not in text


def test_glob_root_only(ctx):
    _tree(ctx)
    text = ctx.text("glob", pattern="*.md", path=str(ctx.root))
    assert "README.md" in text
    assert "app.py" not in text


def test_glob_no_matches(ctx):
    _tree(ctx)
    text = ctx.text("glob", pattern="**/*.rs", path=str(ctx.root))
    assert "(no matches)" in text


def test_glob_limit_and_spill(ctx):
    for index in range(5):
        (ctx.root / f"f{index}.txt").write_text("x", encoding="utf-8")

    meta = ctx.meta("glob", pattern="*.txt", path=str(ctx.root), limit=2)
    assert meta["matches"] == 5
    assert meta["shown"] == 2
    assert meta["truncated"] is True
    assert meta["spill"]
    assert meta["spill"].endswith(".log")


def test_grep_finds_lines(ctx):
    _tree(ctx)
    text = ctx.text("grep", pattern="VALUE", path=str(ctx.root))
    assert "pkg/mod.py:1:VALUE = 42" in text
    assert "hidden.py" not in text


def test_grep_literal(ctx):
    path = ctx.root / "a.txt"
    path.write_text("a.b\naxb\n", encoding="utf-8")

    regex_text = ctx.text("grep", pattern="a.b", path=str(ctx.root))
    assert "axb" in regex_text

    literal_text = ctx.text("grep", pattern="a.b", path=str(ctx.root), literal=True)
    assert "axb" not in literal_text
    assert "a.b" in literal_text


def test_grep_include_filter(ctx):
    _tree(ctx)
    text = ctx.text("grep", pattern="VALUE", path=str(ctx.root), include="mod.py")
    assert "mod.py" in text
    assert "app.py" not in text


def test_grep_no_matches(ctx):
    _tree(ctx)
    text = ctx.text("grep", pattern="nothing-here", path=str(ctx.root))
    assert "(no matches)" in text


def test_grep_invalid_regex(ctx):
    response = ctx.call("grep", pattern="(unclosed", path=str(ctx.root))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_grep_limit_truncates(ctx):
    for index in range(5):
        (ctx.root / f"f{index}.txt").write_text("needle\n", encoding="utf-8")

    meta = ctx.meta("grep", pattern="needle", path=str(ctx.root), limit=2)
    assert meta["matches"] == 2
    assert meta["truncated"] is True
