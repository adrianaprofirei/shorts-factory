"""Claude API wrapper (plain HTTPS, no SDK needed) + robust JSON parsing."""
from __future__ import annotations

import json
import os
import re
import time

import requests

from .config import require_env

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class LLMError(RuntimeError):
    pass


def call_claude(system: str, user: str, model: str, max_tokens: int = 16000,
                retries: int = 4) -> str:
    """Send one message, return the concatenated text blocks.

    Note: on current Claude models, temperature/top_p/top_k are not sent
    (Sonnet 5.5 rejects them with a 400).
    """
    api_key = require_env("ANTHROPIC_API_KEY")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(API_URL, headers=headers, json=body, timeout=300)
        except requests.RequestException as e:  # network hiccup
            last_err = e
        else:
            if r.status_code == 200:
                data = r.json()
                text = "".join(
                    block.get("text", "")
                    for block in data.get("content", [])
                    if block.get("type") == "text"
                )
                if data.get("stop_reason") == "max_tokens":
                    raise LLMError("Raspunsul a fost taiat (max_tokens). Mareste llm.max_tokens in config.yaml.")
                if not text.strip():
                    raise LLMError(f"Raspuns gol de la model: {json.dumps(data)[:500]}")
                return text
            if r.status_code in (429, 500, 502, 503, 504, 529):
                last_err = LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
            else:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:1000]}")
        wait = 2 ** attempt * 3
        print(f"  ... API ocupat, reincerc in {wait}s ({last_err})")
        time.sleep(wait)
    raise LLMError(f"Claude API a esuat dupa {retries + 1} incercari: {last_err}")


def extract_json(text: str) -> dict:
    """Parse the first JSON object in a model reply (tolerates ``` fences)."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError("Modelul nu a returnat JSON.")
    return json.loads(cleaned[start:end + 1])


def ask_json(system: str, user: str, model: str, max_tokens: int = 16000) -> dict:
    """Call Claude and parse JSON; on a parse error, ask once more to repair."""
    reply = call_claude(system, user, model, max_tokens)
    try:
        return extract_json(reply)
    except (LLMError, json.JSONDecodeError) as e:
        repair = (
            f"{user}\n\nYour previous reply could not be parsed as JSON ({e}). "
            "Reply again with ONLY the valid JSON object, nothing else."
        )
        return extract_json(call_claude(system, repair, model, max_tokens))


def have_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
