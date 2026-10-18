import json

import httpx
import pytest

from app import build_corpus, llm
from app.config import settings
from app.index import INDEX_VERSION


def test_build_escribe_indice(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(settings, "index_path", tmp_path / "index.json")
    assert build_corpus.main([]) == 0
    d = json.loads((tmp_path / "index.json").read_text("utf-8"))
    assert len(d["entries"]) >= 8 and d["version"] == INDEX_VERSION


def test_check_no_escribe(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "index_path", tmp_path / "index.json")
    assert build_corpus.main(["--check"]) == 0
    assert not (tmp_path / "index.json").exists()


def test_errores_devuelven_1(tmp_path, monkeypatch):
    bad = tmp_path / "c.txt"
    bad.write_text("### x\nTAGS: a\n--\ntexto\n", "utf-8")
    monkeypatch.setattr(settings, "corpus_path", bad)
    assert build_corpus.main(["--check"]) == 1


def test_llm_anthropic_parsea_uso(cfg, monkeypatch):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "k"

    def fake_post(url, headers, json, timeout):
        assert json["max_tokens"] == 50 and headers["x-api-key"] == "k"
        return httpx.Response(200, json={"content": [{"type": "text", "text": " hola "}],
                                         "usage": {"input_tokens": 11, "output_tokens": 3}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.complete(cfg, "s", "u", 50) == ("hola", 11, 3)


def test_llm_error_http(cfg, monkeypatch):
    cfg.llm_provider, cfg.llm_api_key = "openai", "k"

    def fake_post(url, headers, json, timeout):
        return httpx.Response(429, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(llm.LLMError):
        llm.complete(cfg, "s", "u", 50)


def test_llm_sin_clave(cfg):
    with pytest.raises(llm.LLMError):
        llm.complete(cfg, "s", "u", 50)
