#!/usr/bin/env python3
import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from agent.harness import run_repl
from agent.mcp_client import MCPManager
from agent.ollama_client import OllamaClient
from agent.skills import load_skill_catalog

DEFAULT_SKILLS_DIR = Path(__file__).parent / "vendor" / "agent-skills" / "skills"
DEFAULT_MCP_CONFIG = Path(__file__).parent / "mcp_servers.json"


async def async_main(args: argparse.Namespace) -> None:
    catalog = load_skill_catalog(Path(args.skills_dir))
    client = OllamaClient(model=args.model, host=args.host)

    mcp = None
    mcp_config_path = Path(args.mcp_config)
    if mcp_config_path.exists():
        mcp = MCPManager()
        await mcp.connect_all(mcp_config_path)

    try:
        await run_repl(client, catalog, mcp=mcp)
    finally:
        if mcp:
            await mcp.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local agentic harness for Qwen via Ollama.")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--skills-dir", default=str(DEFAULT_SKILLS_DIR))
    parser.add_argument("--mcp-config", default=str(DEFAULT_MCP_CONFIG))
    args = parser.parse_args()
    load_dotenv(Path(__file__).parent / ".env")
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
