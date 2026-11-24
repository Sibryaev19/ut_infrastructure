"""workspace_info, /health, /info."""
from __future__ import annotations


def test_health(ctx):
    response = ctx.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "workspaces": 1}


def test_info_lists_workspace(ctx):
    payload = ctx.client.get("/info").json()
    assert payload["ok"] is True
    assert payload["meta"]["workspaces"] == [{"name": "ws", "path": str(ctx.root)}]
    assert "path_rules" in payload["meta"]
    assert payload["meta"]["limits"]["read_file"]["max_lines"] > 0


def test_workspace_info_text(ctx):
    text = ctx.text("workspace_info")
    assert "workspaces:" in text
    assert f"ws = {ctx.root}" in text
    assert "reads are unrestricted" in text
