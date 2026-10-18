"""Herramienta del administrador: valida data/corpus.txt y genera data/index.json.

  python -m app.build_corpus                   # valida + indexa (0 tokens)
  python -m app.build_corpus --check           # solo valida (para CI)
  python -m app.build_corpus --sugerir-tags    # OPCIONAL: usa el LLM solo para entradas sin TAGS
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

from . import llm
from .config import settings
from .corpus import parse_corpus, parse_synonyms
from .index import Index, corpus_hash

MAX_ENTRY_CHARS = 1500  # entradas más largas se recortan en el contexto del LLM
CACHE_FILE = settings.index_path.parent / ".tags_cache.json"
OUT_FILE = settings.index_path.parent / "tags_sugeridos.txt"
TAG_SYSTEM = ("Eres un indexador de documentación interna de una planta de manufactura. Responde SOLO con 8 a 12 palabras clave en español, "
              "minúsculas, sin acentos, separadas por comas, que un operador o personal administrativo escribiría para buscar "
              "esto. Incluye sinónimos coloquiales.")


def sugerir_tags(entries, limite: int, todas: bool) -> None:
    if not llm.available(settings):
        print("LLM_API_KEY no configurada: no se pueden sugerir tags.")
        return
    cache = json.loads(CACHE_FILE.read_text("utf-8")) if CACHE_FILE.exists() else {}
    objetivo = [e for e in entries if todas or not e.tags][:limite]
    total_in = total_out = 0
    lines = []
    for e in objetivo:
        key = hashlib.sha1((e.titulo + e.texto[:800]).encode()).hexdigest()
        if key not in cache:
            user = f"Título: {e.titulo}\nPuesto: {e.puesto}\nTexto: {e.texto[:800]}"
            txt, tin, tout = llm.complete(settings, TAG_SYSTEM, user, 60)
            cache[key] = txt.replace("\n", " ").strip()
            total_in, total_out = total_in + tin, total_out + tout
        lines.append(f"{e.id}: {cache[key]}")
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), "utf-8")
    OUT_FILE.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"Sugerencias en {OUT_FILE} (revísalas y pégalas en TAGS). "
          f"Tokens usados: {total_in} entrada + {total_out} salida. Entradas ya en caché: 0 tokens.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="solo validar, no escribir el índice")
    ap.add_argument("--sugerir-tags", action="store_true", help="sugerir TAGS con el LLM (opcional)")
    ap.add_argument("--todas", action="store_true", help="con --sugerir-tags: también entradas que ya tienen tags")
    ap.add_argument("--max-sugerencias", type=int, default=20)
    a = ap.parse_args(argv)

    if not settings.corpus_path.exists():
        print(f"No existe {settings.corpus_path}")
        return 1
    text = settings.corpus_path.read_text("utf-8")
    syn = settings.synonyms_path.read_text("utf-8") if settings.synonyms_path.exists() else ""
    entries, problems = parse_corpus(text)
    for p in problems:
        print(p)
    errors = [p for p in problems if p.level == "error"]

    largas = [e.id for e in entries if len(e.texto) > MAX_ENTRY_CHARS]
    viejas = [e.id for e in entries if (e.age_days() or 0) > settings.stale_days]
    chars = sum(len(e.texto) for e in entries)
    print(f"\nEntradas válidas: {len(entries)} | texto total ≈ {chars} caracteres (≈ {chars // 4} tokens, "
          "NO se envían completos al modelo)")
    if largas:
        print(f"Aviso: entradas > {MAX_ENTRY_CHARS} caracteres (divídelas en dos): {', '.join(largas)}")
    if viejas:
        print(f"Aviso: entradas con más de {settings.stale_days} días sin actualizar: {', '.join(viejas)}")
    if errors:
        print(f"\n{len(errors)} error(es): corrige antes de indexar.")
        return 1

    if not a.check:
        idx = Index.build(entries, parse_synonyms(syn), corpus_hash(text, syn))
        idx.save(settings.index_path)
        print(f"Índice escrito en {settings.index_path} (0 tokens gastados).")
    if a.sugerir_tags:
        sugerir_tags(entries, a.max_sugerencias, a.todas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
