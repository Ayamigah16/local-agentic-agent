#!/usr/bin/env python3
import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from agent.harness import run_repl
from agent.mcp_client import MCPManager
from agent.ollama_client import OllamaClient
from agent.skills import load_skill_catalog, merge_catalogs

VENDOR_DIR = Path(__file__).parent / "vendor"
CORE_SKILLS_DIR = VENDOR_DIR / "agent-skills" / "skills"
CODEX_SKILLS_DIR = VENDOR_DIR / "awesome-codex-skills"
CODEX_COMPOSIO_DIR = CODEX_SKILLS_DIR / "composio-skills"
DEFAULT_MCP_CONFIG = Path(__file__).parent / "mcp_servers.json"


def _load_if_present(skills_dir: Path) -> dict:
    return load_skill_catalog(skills_dir) if skills_dir.is_dir() else {}


def load_catalogs() -> tuple[dict, dict]:
    # "Primary" skills (general-purpose workflows) are small enough to list
    # directly in the system prompt. The Composio automation set is ~800
    # narrow, one-per-SaaS-tool skills — far too many to inline, so they're
    # only reachable via the search_skills tool. See README's "Tool count vs
    # speed" section for why this distinction matters on CPU-only inference.
    primary = merge_catalogs(_load_if_present(CORE_SKILLS_DIR), _load_if_present(CODEX_SKILLS_DIR))
    full = merge_catalogs(primary, _load_if_present(CODEX_COMPOSIO_DIR))
    return primary, full


async def async_main(args: argparse.Namespace) -> None:
    primary_catalog, full_catalog = load_catalogs()
    client = OllamaClient(model=args.model, host=args.host)

    mcp = None
    mcp_config_path = Path(args.mcp_config)
    if mcp_config_path.exists():
        mcp = MCPManager()
        await mcp.connect_all(mcp_config_path)

    try:
        await run_repl(client, primary_catalog, full_catalog, mcp=mcp)
    finally:
        if mcp:
            await mcp.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local agentic harness for Qwen via Ollama.")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--mcp-config", default=str(DEFAULT_MCP_CONFIG))
    args = parser.parse_args()
    load_dotenv(Path(__file__).parent / ".env")
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
