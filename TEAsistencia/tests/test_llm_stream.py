import httpx
import pytest

from app import llm


class FakeResp:
    def __init__(self, lines, status=200):
        self.lines, self.status = lines, status

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError("x", request=httpx.Request("POST", "http://x"), response=httpx.Response(self.status))

    def iter_lines(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def parchear(monkeypatch, lines, status=200):
    def fake(method, url, headers, json, timeout):
        assert method == "POST" and json["stream"] is True
        return FakeResp(lines, status)
    monkeypatch.setattr(httpx, "stream", fake)


def test_stream_anthropic(cfg, monkeypatch):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "k"
    parchear(monkeypatch, [
        "event: message_start",
        'data: {"type":"message_start","message":{"usage":{"input_tokens":50,"output_tokens":1}}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hola "}}',
        'data: {"type":"ping"}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"mundo"}}',
        'data: {"type":"message_delta","usage":{"output_tokens":7}}',
        'data: {"type":"message_stop"}'])
    assert list(llm.stream(cfg, "s", "u", 50)) == [("delta", "Hola "), ("delta", "mundo"), ("usage", (50, 7))]


def test_stream_openai_compatible(cfg, monkeypatch):
    cfg.llm_provider, cfg.llm_api_key = "openai", "k"
    parchear(monkeypatch, [
        'data: {"choices":[{"delta":{"role":"assistant"}}]}',
        'data: {"choices":[{"delta":{"content":"Hola "}}]}',
        'data: {"choices":[{"delta":{"content":"mundo"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":40,"completion_tokens":5}}',
        "data: [DONE]"])
    assert list(llm.stream(cfg, "s", "u", 50)) == [("delta", "Hola "), ("delta", "mundo"), ("usage", (40, 5))]


def test_stream_error_http(cfg, monkeypatch):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "k"
    parchear(monkeypatch, [], status=429)
    with pytest.raises(llm.LLMError):
        list(llm.stream(cfg, "s", "u", 50))


def test_stream_json_corrupto_y_sin_clave(cfg, monkeypatch):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "k"
    parchear(monkeypatch, ["data: {no es json"])
    with pytest.raises(llm.LLMError):
        list(llm.stream(cfg, "s", "u", 50))
    cfg.llm_api_key = ""
    with pytest.raises(llm.LLMError):
        list(llm.stream(cfg, "s", "u", 50))
