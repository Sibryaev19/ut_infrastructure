"""Разовый e2e: mcp_server (stdio) против живого сервера на стенде local_datalab.

Запуск: .venv/bin/python e2e_mcp_stand.py   (из любого каталога)
Ожидание: все 8 тулов отвечают ok:true на живом HTTP через прокси hub'а.
"""

import asyncio
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE = Path(__file__).resolve().parents[2] / "mcp_server"
WS = "/home/datalab/nfs/test"
PROBE = f"{WS}/_e2e_probe.txt"


def env_from_dotenv() -> dict:
    env = dict(os.environ)
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


async def call(session: ClientSession, name: str, args: dict) -> str:
    result = await session.call_tool(name, args)
    return "".join(b.text for b in result.content if hasattr(b, "text"))


async def main() -> None:
    params = StdioServerParameters(
        command=str(BASE / ".venv" / "bin" / "python"),
        args=[str(BASE / "main.py")],
        env=env_from_dotenv(),
        cwd=str(BASE),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("== initialize:", init.server_info.name, init.protocol_version)

            tools = await session.list_tools()
            print("== tools:", sorted(t.name for t in tools.tools))

            checks: list[tuple[str, str, bool]] = []

            out = await call(session, "workspace_info", {})
            checks.append(("workspace_info", out, "test = /home/datalab/nfs/test" in out))

            out = await call(session, "list_dir", {"path": WS})
            checks.append(("list_dir", out, "entries=" in out))

            await call(session, "write_file", {"path": PROBE, "content": "alpha\nbeta\n"})
            out = await call(session, "read_file", {"path": PROBE})
            checks.append(("read_file (probe)", out, "alpha" in out and "beta" in out))

            out = await call(
                session, "edit_file",
                {"path": PROBE, "old_string": "beta", "new_string": "gamma"},
            )
            out2 = await call(session, "read_file", {"path": PROBE})
            checks.append(("edit_file", out + out2, "gamma" in out2 and "beta" not in out2))

            out = await call(session, "glob", {"pattern": "_e2e_probe.txt", "path": WS})
            checks.append(("glob", out, "_e2e_probe" in out))

            out = await call(
                session, "grep", {"pattern": "gamma", "path": WS, "include": "_e2e_probe.txt"}
            )
            checks.append(("grep", out, "gamma" in out))

            out = await call(
                session, "bash",
                {"command": f"cat {PROBE} && hostname", "workdir": WS},
            )
            checks.append(("bash", out, "gamma" in out))

            await call(session, "bash", {"command": f"rm -f {PROBE}", "workdir": WS})

            print()
            failed = 0
            for name, out, ok in checks:
                mark = "PASS" if ok else "FAIL"
                failed += not ok
                print(f"[{mark}] {name}")
                if not ok:
                    print("   ", out[:400])

            print()
            print("E2E:", "ALL PASS" if not failed else f"{failed} FAILED")


if __name__ == "__main__":
    asyncio.run(main())
