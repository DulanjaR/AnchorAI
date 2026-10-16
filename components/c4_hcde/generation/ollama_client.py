"""Calls the fine-tuned HCDE model served by Ollama (fully local, no external API)."""
from __future__ import annotations

import json
import os
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
HCDE_MODEL = os.environ.get("HCDE_MODEL", "hcde")


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 900, timeout: float = 300.0) -> str:
    body = {"model": HCDE_MODEL, "stream": False, "messages": messages,
            "options": {"temperature": temperature, "num_predict": max_tokens}}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["message"]["content"]


def available() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            return any(m["name"].split(":")[0] == HCDE_MODEL for m in json.load(r).get("models", []))
    except Exception:
        return False
