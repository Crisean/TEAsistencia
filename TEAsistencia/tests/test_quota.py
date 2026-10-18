from app.config import Settings
from app.quota import Quota


def mk(**kw):
    s = Settings()
    s.id_salt = "t"
    for k, v in kw.items():
        setattr(s, k, v)
    t = {"now": 1_000_000.0}
    return Quota(s, clock=lambda: t["now"]), t


def test_ritmo_por_minuto():
    q, t = mk(req_per_min=3)
    assert all(q.rate_ok("1.1.1.1", "u") for _ in range(3))
    assert not q.rate_ok("1.1.1.1", "u")
    t["now"] += 61
    assert q.rate_ok("1.1.1.1", "u")


def test_tokens_dia_y_reinicio():
    q, t = mk(user_tokens_day=1000, user_queries_day=10, ip_multiplier=1)
    ok, _ = q.can_spend("ip", "u", 600)
    assert ok
    q.spend("ip", "u", 600)
    ok, why = q.can_spend("ip", "u", 600)
    assert not ok and why == "tokens"
    t["now"] += 86400 * 2
    assert q.can_spend("ip", "u", 600)[0]


def test_tope_global():
    q, _ = mk(global_tokens_day=500)
    assert q.can_spend("a", "x", 600) == (False, "global")


def test_limite_consultas():
    q, _ = mk(user_queries_day=2, ip_multiplier=1)
    for _ in range(2):
        q.spend("ip", "u", 10)
    assert q.can_spend("ip", "u", 10) == (False, "consultas")


def test_limite_de_informes_por_dia():
    q, t = mk(reports_per_day=2, ip_multiplier=1)
    assert q.report_ok("ip", "u") and q.report_ok("ip", "u")
    assert not q.report_ok("ip", "u")
    t["now"] += 86400 * 2
    assert q.report_ok("ip", "u")


def test_gasto_auxiliar_no_cuenta_como_consulta():
    q, _ = mk(user_queries_day=1, ip_multiplier=1)
    q.spend("ip", "u", 80, count_query=False)
    assert q.can_spend("ip", "u", 100)[0] and q.remaining("ip", "u")["consultas"] == 1
    assert q.remaining("ip", "u")["tokens"] == q.s.user_tokens_day - 80
    q.spend("ip", "u", 100)
    assert q.can_spend("ip", "u", 10) == (False, "consultas")
