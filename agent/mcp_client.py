"""Connects to MCP servers over stdio or streamable HTTP and exposes their tools."""

import json
import os
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


def _expand_env(value):
    """Recursively substitutes $VAR / ${VAR} references from the environment
    (e.g. loaded from .env) so tokens never need to live in mcp_servers.json."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


class MCPManager:
    def __init__(self):
        self._stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tool_owner: dict[str, tuple[str, str]] = {}
        self._tool_defs: dict[str, dict] = {}

    async def _try_connect(self, server_name: str, server_conf: dict) -> None:
        # Each attempt gets its own scoped stack so a mid-connection failure
        # (e.g. an unreachable HTTP server) unwinds cleanly within this same
        # task. Only on success do we splice it into the manager's long-lived
        # stack via pop_all() — sharing self._stack across attempts caused
        # anyio cancel-scope errors when a failed connection's cleanup got
        # deferred past this function's return.
        async with AsyncExitStack() as local_stack:
            if "url" in server_conf:
                read, write, _ = await local_stack.enter_async_context(
                    streamablehttp_client(
                        server_conf["url"],
                        headers=server_conf.get("headers"),
                        timeout=server_conf.get("timeout", 5),
                    )
                )
            else:
                params = StdioServerParameters(
                    command=server_conf["command"],
                    args=server_conf.get("args", []),
                    env=server_conf.get("env"),
                )
                read, write = await local_stack.enter_async_context(stdio_client(params))

            session = await local_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = await session.list_tools()

            self._stack.push_async_callback(local_stack.pop_all().aclose)

        self._sessions[server_name] = session
        for tool in tools.tools:
            prefixed = f"mcp_{server_name}_{tool.name}"
            self._tool_owner[prefixed] = (server_name, tool.name)
            self._tool_defs[prefixed] = {
                "type": "function",
                "function": {
                    "name": prefixed,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            }

    async def connect_all(self, config_path: Path) -> None:
        config = _expand_env(json.loads(config_path.read_text()))
        for server_name, server_conf in config.get("mcpServers", {}).items():
            try:
                await self._try_connect(server_name, server_conf)
            except Exception as e:
                print(f"[mcp] skipping '{server_name}': {e}")

    def tool_schemas(self) -> list[dict]:
        return list(self._tool_defs.values())

    def has_tool(self, name: str) -> bool:
        return name in self._tool_owner

    async def call_tool(self, name: str, arguments: dict) -> str:
        server_name, original_name = self._tool_owner[name]
        session = self._sessions[server_name]
        result = await session.call_tool(original_name, arguments)
        parts = [item.text for item in result.content if getattr(item, "text", None)]
        text_out = "\n".join(parts) if parts else "(no text content)"
        return f"Error: {text_out}" if result.isError else text_out

    async def aclose(self) -> None:
        await self._stack.aclose()
