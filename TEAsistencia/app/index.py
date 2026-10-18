"""Índice léxico BM25 con campos ponderados (título, tags, puesto, texto), sinónimos y cobertura.

No usa LLM ni embeddings: construir/actualizar el índice cuesta 0 tokens.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections import Counter
from dataclasses import dataclass

from .corpus import Entry
from .textutil import tokens

INDEX_VERSION = 3
W_TITLE, W_TAGS, W_PUESTO, W_BODY = 3, 4, 2, 1
K1, B = 1.5, 0.6
TAG_BONUS = 0.5
AUDIENCE_PENALTY = 0.5  # multiplicador si el documento es de otro perfil


def corpus_hash(corpus_text: str, syn_text: str = "") -> str:
    return hashlib.sha256((corpus_text + "\n@@\n" + syn_text).encode("utf-8")).hexdigest()


@dataclass
class Hit:
    entry: Entry
    score: float
    coverage: float


class Index:
    def __init__(self, entries, tf, tagsets, df, avgdl, groups, chash, built_at):
        self.entries: list[Entry] = entries
        self.tf: list[dict[str, float]] = tf
        self.tagsets: list[set[str]] = tagsets
        self.df: dict[str, int] = df
        self.avgdl: float = avgdl
        self.groups: list[list[str]] = groups
        self.chash: str = chash
        self.built_at: float = built_at
        self._alts = self._build_alts(groups)
        self._vocab = sorted(df)
        self._exp: dict[str, set[str]] = {}

    # ---------- construcción ----------
    @staticmethod
    def _build_alts(groups: list[list[str]]) -> dict[str, set[str]]:
        alts: dict[str, set[str]] = {}
        for g in groups:
            member_tokens = [tokens(m) for m in g]
            flat = {t for mt in member_tokens for t in mt}
            for mt in member_tokens:
                if len(mt) == 1:  # solo sinónimos de una palabra disparan la expansión
                    alts.setdefault(mt[0], {mt[0]}).update(flat)
        return alts

    @classmethod
    def build(cls, entries: list[Entry], groups: list[list[str]], chash: str) -> Index:
        tf_list, tagsets, df = [], [], Counter()
        for e in entries:
            c: Counter = Counter()
            meta = []  # palabras que la gente usa para pedir datos de contacto de la ficha
            if e.horario:
                meta.append("horario hora abre cierra atencion")
            if e.ubicacion:
                meta.append("ubicacion ubicado queda")
            if e.telefono:
                meta.append("telefono llamar contacto")
            if e.correo:
                meta.append("correo email contacto")
            for w, wt in ((e.titulo, W_TITLE), (" ".join(e.tags), W_TAGS),
                          (f"{e.puesto} {e.categoria}", W_PUESTO),
                          (f"{e.texto} {e.ubicacion} {' '.join(meta)}", W_BODY)):
                for t in tokens(w):
                    c[t] += wt
            tf_list.append(dict(c))
            tagsets.append({t for tag in e.tags for t in tokens(tag)})
            df.update(c.keys())
        dls = [sum(t.values()) for t in tf_list] or [1]
        return cls(entries, tf_list, tagsets, dict(df), sum(dls) / len(dls), groups, chash, time.time())

    def to_dict(self) -> dict:
        return {"version": INDEX_VERSION, "chash": self.chash, "built_at": self.built_at,
                "avgdl": self.avgdl, "groups": self.groups, "df": self.df,
                "entries": [e.to_dict() for e in self.entries], "tf": self.tf,
                "tagsets": [sorted(s) for s in self.tagsets]}

    @classmethod
    def from_dict(cls, d: dict) -> Index:
        if d.get("version") != INDEX_VERSION:
            raise ValueError("versión de índice incompatible")
        entries = [Entry(**e) for e in d["entries"]]
        return cls(entries, d["tf"], [set(s) for s in d["tagsets"]], d["df"], d["avgdl"],
                   d["groups"], d["chash"], d["built_at"])

    def save(self, path) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False), encoding="utf-8")

    # ---------- consulta ----------
    def _expand(self, term: str) -> set[str]:
        """Sinónimos + variantes por prefijo común (documentacion ~ documento, entrego ~ entrega)."""
        if term in self._exp:
            return self._exp[term]
        out = set(self._alts.get(term, {term}))
        for a in list(out):
            if len(a) < 6:
                continue
            for v in self._vocab:
                if v == a or len(v) < 5:
                    continue
                need = max(5, int(0.75 * min(len(a), len(v))))
                if len(os.path.commonprefix([a, v])) >= need:
                    out.add(v)
        self._exp[term] = out
        return out

    def query_terms(self, query: str) -> list[str]:
        seen, out = set(), []
        for t in tokens(query):
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def _idf(self, term: str) -> float:
        n = len(self.entries)
        d = self.df.get(term, 0)
        return math.log(1 + (n - d + 0.5) / (d + 0.5))

    def search(self, query: str, perfil: str | None = None, k: int = 3) -> list[Hit]:
        terms = self.query_terms(query)
        if not terms or not self.entries:
            return []
        hits: list[Hit] = []
        for i, e in enumerate(self.entries):
            tf, tags = self.tf[i], self.tagsets[i]
            dl = sum(tf.values()) or 1
            norm = K1 * (1 - B + B * dl / self.avgdl)
            score, matched = 0.0, 0
            for t in terms:
                best, hit = 0.0, False
                for a in self._expand(t):
                    f = tf.get(a, 0)
                    if f:
                        hit = True
                        best = max(best, self._idf(a) * f * (K1 + 1) / (f + norm))
                        if a in tags:
                            best += TAG_BONUS
                if hit:
                    matched += 1
                    score += best
            if matched == 0:
                continue
            if perfil in ("operador", "administrativo") and "todos" not in e.audiencia and perfil not in e.audiencia:
                score *= AUDIENCE_PENALTY
            hits.append(Hit(e, score, matched / len(terms)))
        hits.sort(key=lambda h: (h.score, h.coverage), reverse=True)
        return hits[:k]
