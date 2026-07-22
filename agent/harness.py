"""REPL agent loop: local Qwen model + Agent Skills + MCP tools + basic tools."""

import asyncio
import json

import requests

from .mcp_client import MCPManager
from .ollama_client import OllamaClient
from .skills import Skill, catalog_summary
from .tools import build_tool_schemas, dispatch_tool_call

MAX_TOOL_ITERATIONS = 8


def build_system_prompt(catalog: dict[str, Skill], has_mcp: bool) -> str:
    mcp_note = (
        " Some tools come from connected MCP servers (prefixed mcp_) — use them "
        "like any other tool."
        if has_mcp
        else ""
    )
    return (
        "You are a local coding agent running on the user's machine.\n\n"
        "Available skills (each encodes a workflow for a specific kind of task):\n"
        f"{catalog_summary(catalog)}\n\n"
        "Before starting non-trivial work, call load_skill with the name of the "
        "skill that best matches the task, then follow its process. You also have "
        "read_file, write_file, and run_shell tools to inspect and modify the "
        "user's project. write_file and run_shell require the user's confirmation, "
        f"so explain what you're about to do before calling them.{mcp_note}"
    )


def _normalize_tool_call_args(tool_calls: list[dict]) -> None:
    # Ollama sometimes returns arguments as a JSON string rather than an
    # object; normalize before storing so later turns always send back a
    # parsed object, which is what the API expects.
    for call in tool_calls:
        args = call["function"]["arguments"]
        if isinstance(args, str):
            call["function"]["arguments"] = json.loads(args)


async def _execute_tool_call(call: dict, catalog: dict[str, Skill], mcp: MCPManager | None) -> dict:
    fn = call["function"]
    name = fn["name"]
    args = fn["arguments"]
    print(f"\n[tool] {name}({args})")
    if mcp and mcp.has_tool(name):
        result = await mcp.call_tool(name, args)
    else:
        result = dispatch_tool_call(name, args, catalog)
    return {"role": "tool", "tool_name": name, "content": result}


async def _run_turn(
    client: OllamaClient,
    tool_schemas: list[dict],
    messages: list[dict],
    catalog: dict[str, Skill],
    mcp: MCPManager | None,
) -> None:
    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            reply = await asyncio.to_thread(client.chat, messages, tool_schemas)
        except requests.RequestException as e:
            print(f"\n[error] Ollama request failed: {e}\n")
            return

        tool_calls = reply.get("tool_calls")
        if not tool_calls:
            messages.append(reply)
            print(f"\n{reply.get('content', '')}\n")
            return

        _normalize_tool_call_args(tool_calls)
        messages.append(reply)

        for call in tool_calls:
            messages.append(await _execute_tool_call(call, catalog, mcp))

    print("\n[stopped: too many tool iterations for this turn]\n")


async def run_repl(client: OllamaClient, catalog: dict[str, Skill], mcp: MCPManager | None = None) -> None:
    tool_schemas = build_tool_schemas(catalog)
    if mcp:
        tool_schemas += mcp.tool_schemas()
    messages = [{"role": "system", "content": build_system_prompt(catalog, has_mcp=bool(mcp))}]

    mcp_count = len(mcp.tool_schemas()) if mcp else 0
    print(f"Local agent ready (model={client.model}, {len(catalog)} skills, {mcp_count} MCP tools).")
    print("Type your task, or 'exit' to quit.\n")

    while True:
        try:
            user_input = (await asyncio.to_thread(input, "> ")).strip()
        except EOFError:
            break
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        await _run_turn(client, tool_schemas, messages, catalog, mcp)
