"""Límites de uso en memoria: ritmo por minuto, tokens y consultas por día, tope global.

Cada usuario se identifica por un id anónimo del navegador y por IP (ambos con hash salado,
nunca se guardan en claro). Los contadores se reinician cada día y al reiniciar el servicio.
El tope real de gasto debe configurarse TAMBIÉN en el panel del proveedor de IA.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from .config import Settings


class Quota:
    def __init__(self, s: Settings, clock=time.time):
        self.s = s
        self.clock = clock
        self._day = self._today()
        self.tokens: dict[str, int] = defaultdict(int)
        self.queries: dict[str, int] = defaultdict(int)
        self.reports: dict[str, int] = defaultdict(int)
        self.global_tokens = 0
        self.global_queries = 0
        self._recent: dict[str, deque] = defaultdict(deque)

    def _today(self) -> str:
        try:
            from zoneinfo import ZoneInfo
            return datetime.fromtimestamp(self.clock(), ZoneInfo(self.s.timezone)).strftime("%Y-%m-%d")
        except (ImportError, KeyError, ValueError, OSError):
            return datetime.fromtimestamp(self.clock(), UTC).strftime("%Y-%m-%d")

    def _roll(self) -> None:
        d = self._today()
        if d != self._day:
            self._day = d
            self.tokens.clear()
            self.queries.clear()
            self.reports.clear()
            self.global_tokens = 0
            self.global_queries = 0
        if len(self._recent) > 20000:
            self._recent.clear()

    def _h(self, kind: str, value: str) -> str:
        return kind + hashlib.sha256((self.s.id_salt + value).encode()).hexdigest()[:16]

    def _keys(self, ip: str, cid: str) -> list[tuple[str, int]]:
        m = max(1, self.s.ip_multiplier)
        return [(self._h("c", cid or "anon"), 1), (self._h("i", ip or "?"), m)]

    # --- ritmo ---
    def rate_ok(self, ip: str, cid: str) -> bool:
        self._roll()
        now = self.clock()
        ok = True
        for key, mult in self._keys(ip, cid):
            q = self._recent[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.s.req_per_min * mult:
                ok = False
        if ok:
            for key, _ in self._keys(ip, cid):
                self._recent[key].append(now)
        return ok

    # --- gasto de tokens (solo consultas que llaman al LLM) ---
    def can_spend(self, ip: str, cid: str, estimate: int) -> tuple[bool, str]:
        self._roll()
        if self.global_tokens + estimate > self.s.global_tokens_day:
            return False, "global"
        for key, mult in self._keys(ip, cid):
            if self.queries[key] >= self.s.user_queries_day * mult:
                return False, "consultas"
            if self.tokens[key] + estimate > self.s.user_tokens_day * mult:
                return False, "tokens"
        return True, ""

    def spend(self, ip: str, cid: str, tokens_used: int, count_query: bool = True) -> None:
        """Descuenta tokens. Las llamadas auxiliares (reformular) no cuentan como una consulta del día."""
        self._roll()
        self.global_tokens += tokens_used
        if count_query:
            self.global_queries += 1
        for key, _ in self._keys(ip, cid):
            self.tokens[key] += tokens_used
            if count_query:
                self.queries[key] += 1

    def report_ok(self, ip: str, cid: str) -> bool:
        """Máximo de informes 'sin respuesta' por usuario y día (evita spam al administrador)."""
        self._roll()
        keys = self._keys(ip, cid)
        if any(self.reports[k] >= self.s.reports_per_day * m for k, m in keys):
            return False
        for k, _ in keys:
            self.reports[k] += 1
        return True

    def remaining(self, ip: str, cid: str) -> dict:
        self._roll()
        key = self._keys(ip, cid)[0][0]
        return {"tokens": max(0, self.s.user_tokens_day - self.tokens[key]),
                "consultas": max(0, self.s.user_queries_day - self.queries[key])}

    def stats(self) -> dict:
        self._roll()
        return {"dia": self._day, "tokens_globales": self.global_tokens,
                "consultas_llm": self.global_queries, "tope_global": self.s.global_tokens_day}
