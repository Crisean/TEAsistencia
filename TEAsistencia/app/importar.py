"""Importa un documento (PDF, HTML, TXT, MD) y propone fichas para el corpus usando IA.

  python -m app.importar reglamento.pdf --dry-run     # solo muestra fragmentos y costo estimado (0 tokens)
  python -m app.importar reglamento.pdf               # llama a la IA y escribe data/propuestas.txt
Revisa data/propuestas.txt, copia las fichas buenas a data/corpus.txt y ejecuta: python -m app.build_corpus
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import llm
from .admin_ai import extraer_texto, importar_texto, partir
from .config import settings
from .corpus import parse_corpus

TOKENS_PROMPT_Y_SALIDA = 450 + 700  # instrucciones + fichas generadas por fragmento (estimación)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivo")
    ap.add_argument("--dry-run", action="store_true", help="no llama a la IA: muestra fragmentos y costo estimado")
    ap.add_argument("--max-chunks", type=int, default=None)
    ap.add_argument("--salida", default=str(settings.corpus_path.parent / "propuestas.txt"))
    a = ap.parse_args(argv)

    ruta = Path(a.archivo)
    if not ruta.exists():
        print(f"No existe {ruta}")
        return 1
    try:
        texto = extraer_texto(ruta.name, ruta.read_bytes())
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    tope = a.max_chunks or settings.import_max_chunks
    chunks = partir(texto, settings.import_chunk_chars)
    usados = min(len(chunks), tope)
    est = sum(len(c) for c in chunks[:usados]) // 3 + usados * TOKENS_PROMPT_Y_SALIDA
    print(f"{len(texto)} caracteres → {len(chunks)} fragmentos (se procesarán {usados}). Costo estimado ≈ {est} tokens.")
    if a.dry_run:
        return 0
    if not llm.available(settings):
        print("Configura LLM_API_KEY para usar la IA (o usa --dry-run).")
        return 1
    existentes = {e.id for e in parse_corpus(settings.corpus_path.read_text("utf-8"))[0]} if settings.corpus_path.exists() else set()
    prop, res = importar_texto(texto, ruta.name, llm.complete, settings, existentes, max_chunks=a.max_chunks)
    for aviso in res["avisos"]:
        print("Aviso:", aviso)
    if prop:
        Path(a.salida).write_text(prop + "\n", "utf-8")
        print(f"{res['fichas']} fichas propuestas en {a.salida}. Tokens: {res['tokens_entrada']} entrada + {res['tokens_salida']} salida.")
    return 0 if prop else 1


if __name__ == "__main__":
    sys.exit(main())
