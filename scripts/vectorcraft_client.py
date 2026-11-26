"""
A small client for VectorCraft's MCP server: launch `vectorcraft-cli mcp` over
stdio with the `mcp` SDK and call its tools. No Claude in the loop.

    async with VectorCraft() as vc:
        vc_doc = await vc.run("document.open", {"path": ...})
        out = await vc.run("document.export", {"format": "jpg", "quality": 85})

The server runs headless: the VectorCraft app does not need to be open.
It may read only VECTORCRAFT_READ_ROOT and write only VECTORCRAFT_WRITE_ROOT
(it takes one folder of each). Exports without a path come back as base64,
so callers write files themselves.
"""
from __future__ import annotations

import base64
import json
import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLI = os.getenv("VECTORCRAFT_CLI", str(Path.home() / ".local/bin/vectorcraft-cli"))
READ_ROOT = os.getenv("VECTORCRAFT_READ_ROOT", str(ROOT / "assets" / "templates"))
WRITE_ROOT = os.getenv("VECTORCRAFT_WRITE_ROOT", str(ROOT / "data" / "spotify" / "covers"))
CALL_TIMEOUT_S = float(os.getenv("VECTORCRAFT_TIMEOUT_S", "60"))


class VectorCraftError(RuntimeError):
    pass


def _parse(result: Any) -> Any:
    """A tool result's first text block, as JSON when it is JSON."""
    texts = [c.text for c in (result.content or []) if getattr(c, "type", "") == "text"]
    text = texts[0] if texts else ""
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        raise VectorCraftError(text or "VectorCraft tool error")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


class VectorCraft:
    def __init__(self, *, cli: str | None = None, read_root: str | None = None, write_root: str | None = None):
        # read the environment per instance so tests and callers can point it elsewhere
        self.cli = cli or os.getenv("VECTORCRAFT_CLI", CLI)
        self.read_root = read_root or os.getenv("VECTORCRAFT_READ_ROOT", READ_ROOT)
        self.write_root = write_root or os.getenv("VECTORCRAFT_WRITE_ROOT", WRITE_ROOT)
        self._stack: AsyncExitStack | None = None
        self.session = None

    async def __aenter__(self) -> "VectorCraft":
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if not Path(self.cli).exists():
            raise VectorCraftError(f"vectorcraft-cli not found at {self.cli}")
        params = StdioServerParameters(command=self.cli, args=[
            "mcp", "--automation-read-root", self.read_root, "--automation-write-root", self.write_root])
        self._stack = AsyncExitStack()
        try:
            with open(os.devnull, "w") as devnull:   # the CLI's banner goes to stderr
                read, write = await self._stack.enter_async_context(stdio_client(params, errlog=devnull))
            self.session = await self._stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc) -> None:
        if self._stack:
            await self._stack.aclose()

    async def tool(self, name: str, args: dict[str, Any] | None = None) -> Any:
        import anyio
        with anyio.fail_after(CALL_TIMEOUT_S):
            return _parse(await self.session.call_tool(name, args or {}))

    async def run(self, command_id: str, params: dict[str, Any] | None = None) -> Any:
        """Run a menu command (command_list shows them and their params)."""
        return await self.tool("command_run", {"id": command_id, "params": params or {}})

    async def batch(self, steps: list[dict[str, Any]]) -> Any:
        return await self.tool("command_batch", {"steps": steps})

    async def export_bytes(self, fmt: str, **opts: Any) -> bytes:
        """Export the open document with no path and return the file's bytes."""
        out = await self.run("document.export", {"format": fmt, **opts})
        if not isinstance(out, dict) or not out.get("dataBase64"):
            raise VectorCraftError(f"export returned no data: {str(out)[:300]}")
        return base64.b64decode(out["dataBase64"])
