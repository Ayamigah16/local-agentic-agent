"""Tool schemas and implementations for the local agent loop."""

import subprocess
from pathlib import Path

from .skills import Skill
from .token_api_tools import TOKEN_API_TOOLS

SHELL_TIMEOUT_SECONDS = 60


def build_tool_schemas(catalog: dict[str, Skill]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "load_skill",
                "description": "Load the full instructions for a named skill from the skill catalog.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": list(catalog.keys()),
                            "description": "Exact skill name from the catalog.",
                        }
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a text file, relative to the current working directory.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a text file, relative to the current working directory. Asks the user for confirmation before writing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_shell",
                "description": "Run a shell command in the current working directory. Asks the user for confirmation before running.",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        },
        *[tool.schema() for tool in TOKEN_API_TOOLS],
    ]


def _confirm(prompt: str) -> bool:
    reply = input(f"{prompt} [y/N] ").strip().lower()
    return reply == "y"


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _load_skill(args: dict, catalog: dict[str, Skill]) -> str:
    skill = catalog.get(args["name"])
    if skill is None:
        return f"Error: no skill named '{args['name']}' in the catalog."
    return skill.body


def _read_file(args: dict, catalog: dict[str, Skill]) -> str:
    path = _resolve(args["path"])
    try:
        return path.read_text()
    except OSError as e:
        return f"Error reading {path}: {e}"


def _write_file(args: dict, catalog: dict[str, Skill]) -> str:
    path = _resolve(args["path"])
    if not _confirm(f"\n[agent wants to write {path}]\nAllow?"):
        return "User declined this write_file call."
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args["content"])
    return f"Wrote {path}"


def _run_shell(args: dict, catalog: dict[str, Skill]) -> str:
    command = args["command"]
    if not _confirm(f"\n[agent wants to run] $ {command}\nAllow?"):
        return "User declined this run_shell call."
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_SECONDS,
        )
        output = result.stdout + result.stderr
        return output[-4000:] if output else f"(no output, exit code {result.returncode})"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {SHELL_TIMEOUT_SECONDS}s."


_HANDLERS = {
    "load_skill": _load_skill,
    "read_file": _read_file,
    "write_file": _write_file,
    "run_shell": _run_shell,
    **{tool.name: (lambda args, catalog, _t=tool: _t.call(args)) for tool in TOKEN_API_TOOLS},
}


def dispatch_tool_call(name: str, args: dict, catalog: dict[str, Skill]) -> str:
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool '{name}'."
    return handler(args, catalog)
