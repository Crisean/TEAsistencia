from app import importar, llm
from app.config import settings

DOC = ("Servicio de Idiomas. Ofrece cursos de inglés y francés para el personal. " * 6)
FICHA = "### idiomas\nTITULO: Idiomas\nTAGS: idiomas, ingles\nPREGUNTA: ¿Cómo me inscribo a inglés?\n--\nCursos de inglés y francés."


def preparar(monkeypatch, tmp_path, texto=DOC):
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("### a-uno\nTITULO: Uno\nTAGS: x\nACTUALIZADO: 2026-01-01\n--\ntexto\n", "utf-8")
    monkeypatch.setattr(settings, "corpus_path", corpus)
    doc = tmp_path / "idiomas.txt"
    doc.write_text(texto, "utf-8")
    return doc


def test_dry_run_no_llama_a_la_ia(monkeypatch, tmp_path, capsys):
    doc = preparar(monkeypatch, tmp_path)
    monkeypatch.setattr(llm, "complete", lambda *a: (_ for _ in ()).throw(AssertionError("no debe llamar")))
    assert importar.main([str(doc), "--dry-run"]) == 0
    assert "Costo estimado" in capsys.readouterr().out


def test_sin_clave_no_importa(monkeypatch, tmp_path, capsys):
    doc = preparar(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "llm_api_key", "")
    assert importar.main([str(doc)]) == 1 and "LLM_API_KEY" in capsys.readouterr().out


def test_importa_y_escribe_propuesta(monkeypatch, tmp_path, capsys):
    doc = preparar(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_api_key", "x")
    monkeypatch.setattr(llm, "complete", lambda s, sy, u, m: (FICHA, 400, 90))
    salida = tmp_path / "prop.txt"
    assert importar.main([str(doc), "--salida", str(salida)]) == 0
    assert "### idiomas" in salida.read_text("utf-8") and "400 entrada + 90 salida" in capsys.readouterr().out


def test_errores_de_archivo(monkeypatch, tmp_path, capsys):
    preparar(monkeypatch, tmp_path)
    assert importar.main([str(tmp_path / "nada.txt")]) == 1
    corto = tmp_path / "corto.txt"
    corto.write_text("hola", "utf-8")
    assert importar.main([str(corto)]) == 1 and "extraer texto" in capsys.readouterr().out
