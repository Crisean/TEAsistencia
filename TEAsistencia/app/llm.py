"""Cliente LLM mínimo (httpx). Devuelve (texto, tokens_entrada, tokens_salida)."""
from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from .config import Settings


class LLMError(Exception):
    pass


def available(s: Settings) -> bool:
    return s.llm_provider in ("anthropic", "openai") and bool(s.llm_api_key)


def complete(s: Settings, system: str, user: str, max_tokens: int) -> tuple[str, int, int]:
    if not available(s):
        raise LLMError("LLM no configurado")
    try:
        if s.llm_provider == "anthropic":
            r = httpx.post(
                (s.llm_base_url or "https://api.anthropic.com") + "/v1/messages",
                headers={"x-api-key": s.llm_api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": s.model_name, "max_tokens": max_tokens, "temperature": 0,
                      "system": system, "messages": [{"role": "user", "content": user}]},
                timeout=s.llm_timeout_s)
            r.raise_for_status()
            d = r.json()
            text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
            u = d.get("usage", {})
            return text.strip(), int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
        # openai-compatible
        r = httpx.post(
            (s.llm_base_url or "https://api.openai.com/v1") + "/chat/completions",
            headers={"Authorization": f"Bearer {s.llm_api_key}"},
            json={"model": s.model_name, "max_tokens": max_tokens, "temperature": 0,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=s.llm_timeout_s)
        r.raise_for_status()
        d = r.json()
        u = d.get("usage", {})
        return (d["choices"][0]["message"]["content"].strip(),
                int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)))
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise LLMError(f"{type(e).__name__}") from e


def stream(s: Settings, system: str, user: str, max_tokens: int) -> Iterator[tuple[str, object]]:
    """Respuesta en streaming. Emite ("delta", texto) y al final ("usage", (tokens_entrada, tokens_salida))."""
    if not available(s):
        raise LLMError("LLM no configurado")
    tin = tout = 0
    try:
        if s.llm_provider == "anthropic":
            url = (s.llm_base_url or "https://api.anthropic.com") + "/v1/messages"
            headers = {"x-api-key": s.llm_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            body = {"model": s.model_name, "max_tokens": max_tokens, "temperature": 0, "stream": True,
                    "system": system, "messages": [{"role": "user", "content": user}]}
        else:
            url = (s.llm_base_url or "https://api.openai.com/v1") + "/chat/completions"
            headers = {"Authorization": f"Bearer {s.llm_api_key}"}
            body = {"model": s.model_name, "max_tokens": max_tokens, "temperature": 0, "stream": True,
                    "stream_options": {"include_usage": True},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        with httpx.stream("POST", url, headers=headers, json=body, timeout=s.llm_timeout_s) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                ev = json.loads(data)
                if s.llm_provider == "anthropic":
                    t = ev.get("type")
                    if t == "message_start":
                        tin = int(ev["message"].get("usage", {}).get("input_tokens", 0))
                    elif t == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                        yield "delta", ev["delta"]["text"]
                    elif t == "message_delta":
                        tout = int(ev.get("usage", {}).get("output_tokens", tout))
                else:
                    if ev.get("usage"):
                        tin = int(ev["usage"].get("prompt_tokens", 0))
                        tout = int(ev["usage"].get("completion_tokens", 0))
                    for ch in ev.get("choices", []):
                        piece = (ch.get("delta") or {}).get("content")
                        if piece:
                            yield "delta", piece
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise LLMError(f"{type(e).__name__}") from e
    yield "usage", (tin, tout)
