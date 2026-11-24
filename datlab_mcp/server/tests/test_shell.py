"""bash: код возврата, workdir, отсутствие состояния, таймаут, spill."""
from __future__ import annotations

import pytest

from conftest import posix_only

pytestmark = posix_only


def test_bash_echo(ctx):
    meta = ctx.meta("bash", command="echo hello", workdir=str(ctx.root))
    assert meta["exit_code"] == 0
    assert meta["timed_out"] is False
    assert "hello" in ctx.text("bash", command="echo hello", workdir=str(ctx.root))


def test_bash_exit_code(ctx):
    meta = ctx.meta("bash", command="exit 3", workdir=str(ctx.root))
    assert meta["exit_code"] == 3


def test_bash_stderr(ctx):
    text = ctx.text("bash", command="echo oops >&2", workdir=str(ctx.root))
    assert "--- stderr" in text
    assert "oops" in text


def test_bash_workdir(ctx):
    text = ctx.text("bash", command="pwd", workdir=str(ctx.root))
    assert str(ctx.root) in text


def test_bash_cd_does_not_persist(ctx):
    ctx.text("bash", command="cd /", workdir=str(ctx.root))
    text = ctx.text("bash", command="pwd", workdir=str(ctx.root))
    assert str(ctx.root) in text


def test_bash_timeout_kills_process(ctx):
    meta = ctx.meta("bash", command="sleep 30", workdir=str(ctx.root), timeout_ms=1000)
    assert meta["timed_out"] is True
    assert meta["duration_ms"] < 10_000


def test_bash_large_output_spills(ctx):
    meta = ctx.meta("bash", command="seq 1 20000", workdir=str(ctx.root))
    assert meta["exit_code"] == 0
    assert meta["stdout_spill"]
    text = ctx.text("bash", command="seq 1 20000", workdir=str(ctx.root))
    assert "truncated; full log:" in text


def test_bash_empty_command_rejected(ctx):
    response = ctx.call("bash", command="   ", workdir=str(ctx.root))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_bash_missing_workdir_rejected(ctx):
    response = ctx.call("bash", command="pwd", workdir=str(ctx.root / "missing"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
