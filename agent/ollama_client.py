"""Thin wrapper over the local Ollama /api/chat endpoint."""

import requests


class OllamaClient:
    def __init__(
        self,
        model: str,
        host: str = "http://127.0.0.1:11434",
        num_thread: int = 8,
        num_ctx: int = 8192,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.num_thread = num_thread
        self.num_ctx = num_ctx

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_thread": self.num_thread, "num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = tools
        response = requests.post(f"{self.host}/api/chat", json=payload, timeout=600)
        response.raise_for_status()
        return response.json()["message"]
