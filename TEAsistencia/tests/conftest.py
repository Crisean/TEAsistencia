import pytest

from app.config import BASE, Settings


@pytest.fixture
def cfg(tmp_path):
    s = Settings()
    s.corpus_path = BASE / "data" / "corpus.txt"
    s.synonyms_path = BASE / "data" / "sinonimos.txt"
    s.index_path = tmp_path / "index.json"   # fuerza reconstrucción en memoria
    s.llm_provider = "none"
    s.llm_api_key = ""
    s.admin_token = "token-de-prueba"
    return s
