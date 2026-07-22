"""Declarative registry of 'GET a REST API with a personal access token' tools.

Use this for services that expose a plain token-authenticated REST API but
whose MCP server (if any) is OAuth-gated or allowlist-restricted, so a
homegrown client can't use it (see README's "Adding MCP servers" section).
"""

import os
from dataclasses import dataclass

import requests


@dataclass
class TokenApiTool:
    name: str
    base_url: str
    token_env_var: str
    header_name: str
    header_format: str  # e.g. "Bearer {token}" or just "{token}"
    token_help: str
    description: str

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": f"API path after {self.base_url}/",
                        },
                        "params": {
                            "type": "object",
                            "description": "Optional query parameters.",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["path"],
                },
            },
        }

    def call(self, args: dict) -> str:
        token = os.environ.get(self.token_env_var)
        if not token:
            return f"Error: {self.token_env_var} is not set. {self.token_help}"
        path = args["path"].lstrip("/")
        try:
            response = requests.get(
                f"{self.base_url}/{path}",
                headers={self.header_name: self.header_format.format(token=token)},
                params=args.get("params"),
                timeout=30,
            )
            response.raise_for_status()
            return response.text[:8000]
        except requests.RequestException as e:
            return f"Error calling {self.name}: {e}"


TOKEN_API_TOOLS = [
    TokenApiTool(
        name="figma_api_get",
        base_url="https://api.figma.com/v1",
        token_env_var="FIGMA_TOKEN",
        header_name="X-Figma-Token",
        header_format="{token}",
        token_help="Generate one at figma.com > account menu > Settings > Security > Personal access tokens.",
        description=(
            "Read-only GET against the Figma REST API. Use for file contents, "
            "nodes, comments, images, projects."
        ),
    ),
    TokenApiTool(
        name="vercel_api_get",
        base_url="https://api.vercel.com",
        token_env_var="VERCEL_TOKEN",
        header_name="Authorization",
        header_format="Bearer {token}",
        token_help="Generate one at vercel.com > Account Settings > Tokens.",
        description=(
            "Read-only GET against the Vercel REST API. Use for projects, "
            "deployments, domains, env vars, etc."
        ),
    ),
]
