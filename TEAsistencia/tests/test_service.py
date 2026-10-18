from app import llm
from app.service import Service

Q_LLM = "¿Cómo entrego la solicitud de vacaciones en el edificio?"
Q_LLM2 = "¿Cómo entrego la aclaración de tiempo extra en el edificio?"


def fake_llm(texto="Entrega tu solicitud en Recursos Humanos [recursos-humanos].", tin=700, tout=60, calls=None):
    def f(s, system, user, max_tokens):
        if calls is not None:
            calls.append((system, user, max_tokens))
        return texto, tin, tout
    return f


def con_llm(cfg, **kw):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    return Service(cfg, llm_fn=fake_llm(**kw))


def test_emergencia_deriva_sin_tokens(cfg):
    r = Service(cfg).responder("hay un incendio en la linea 5", "todos", "ip", "c")
    assert r["tipo"] == "derivacion" and "911" in r["respuesta"] and r["fichas"] == []


def test_salud_deriva(cfg):
    r = Service(cfg).responder("que medicamento me tomo para el dolor de cabeza", "todos", "ip", "c")
    assert r["tipo"] == "derivacion" and "médica" in r["respuesta"]


def test_abstencion_sin_evidencia_solo_reformula(cfg):
    calls = []
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    s = Service(cfg, llm_fn=fake_llm(texto="zzz qqq", calls=calls))
    r = s.responder("cuanto cuesta un boleto de avion a Paris", "todos", "ip", "c")
    assert r["tipo"] == "abstencion" and not s.reportes
    assert len(calls) == 1 and calls[0][2] == 40  # solo la reformulación barata, nunca la respuesta larga


def test_sin_llm_responde_directo_con_ficha(cfg):
    r = Service(cfg).responder("horario comedor", "todos", "ip", "c")
    assert r["tipo"] == "directa"
    assert r["fichas"][0]["id"] == "comedor" and r["fichas"][0]["horario"]


def test_llm_cita_validada_y_tokens_contados(cfg):
    calls = []
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    s = Service(cfg, llm_fn=fake_llm(calls=calls))
    r = s.responder(Q_LLM, "operador", "ip", "c")
    assert r["tipo"] == "llm" and r["verificacion"] == "verificada"
    assert "[1]" in r["respuesta"] and r["fuentes"][0]["id"] == "recursos-humanos"
    assert r["uso"]["tokens_consulta"] == 760
    _system, user, mx = calls[0]
    assert mx == cfg.max_output_tokens and len(user) < cfg.max_context_chars + 600
    assert "@" not in user and "Ext. 11" not in user  # correos y teléfonos nunca se envían al LLM


def test_cita_inventada_se_descarta(cfg):
    s = con_llm(cfg, texto="Ve a la oficina [no-existe].")
    r = s.responder(Q_LLM, "operador", "ip", "c")
    assert r["verificacion"] == "no_verificada" and "[no-existe]" not in r["respuesta"]


def test_cache_evita_segunda_llamada(cfg):
    calls = []
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    s = Service(cfg, llm_fn=fake_llm(calls=calls))
    q = Q_LLM
    s.responder(q, "operador", "ip", "c")
    r2 = s.responder("Como entrego la solicitud de vacaciones en el edificio", "operador", "ip", "c")
    assert len(calls) == 1 and r2.get("desde_cache") and r2["uso"]["tokens_consulta"] == 0


def test_limite_diario_degrada_a_ficha(cfg):
    cfg.user_queries_day = 1
    s = con_llm(cfg)
    s.responder(Q_LLM, "operador", "ip", "c")
    r = s.responder(Q_LLM2, "operador", "ip", "c")
    assert r["tipo"] == "directa" and r["limite"] is True
    txt = r["respuesta"]
    assert "límite" in txt and "comunidad" in txt and "comprensión" in txt and "Mientras tanto" in txt
    assert "Nómina" in txt  # mientras tanto se muestra la ficha relevante


def test_fallo_llm_degrada(cfg):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"

    def boom(*a, **k):
        raise llm.LLMError("timeout")
    r = Service(cfg, llm_fn=boom).responder(Q_LLM, "todos", "ip", "c")
    assert r["tipo"] == "directa" and r["fichas"]


def test_aviso_de_vigencia(cfg):
    cfg.stale_days = -1  # fuerza el aviso: cualquier ficha con fecha se considera vencida
    r = Service(cfg).responder("verificacion de pulsera esd", "operador", "ip", "c")
    assert any("actualizó hace" in a for a in r["advertencias"])


def test_consulta_clara_va_directa_aun_con_llm_y_cuesta_0_tokens(cfg):
    calls = []
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    s = Service(cfg, llm_fn=fake_llm(calls=calls))
    r = s.responder("horario comedor", "todos", "ip", "c")
    assert r["tipo"] == "directa" and not calls and r["uso"]["tokens_consulta"] == 0


def test_contexto_respeta_presupuesto(cfg):
    cfg.max_context_chars = 600
    s = Service(cfg)
    hits = s.index.search("vacaciones nomina comedor wifi", "todos", 3)
    assert len(s._context(hits)) <= 600


def test_reportar_anonimiza_y_agrupa(cfg):
    s = Service(cfg)
    ok, msg = s.reportar("¿Dónde pago? mi correo es ana.perez@gmail.com y mi cel 662 123 4567", "ip", "c1")
    assert ok and "Gracias" in msg
    rec = next(iter(s.reportes.values()))
    assert "@" not in rec["pregunta"] and "4567" not in rec["pregunta"] and "[dato omitido]" in rec["pregunta"]
    s.reportar("¿Dónde pago? mi correo es ana.perez@gmail.com y mi cel 662 123 4567", "ip", "c2")
    assert len(s.reportes) == 1 and rec["veces"] == 2


def test_reportar_vacio_y_limite_diario(cfg):
    cfg.reports_per_day, cfg.ip_multiplier = 2, 1
    s = Service(cfg)
    assert s.reportar("   ", "ip", "c")[0] is False
    assert s.reportar("pregunta uno", "ip", "c")[0] and s.reportar("pregunta dos", "ip", "c")[0]
    ok, msg = s.reportar("pregunta tres", "ip", "c")
    assert ok is False and "varios informes" in msg


def test_reportar_envia_webhook_y_tolera_fallos(cfg, monkeypatch):
    import httpx
    enviados = []
    cfg.report_webhook_url = "https://hooks.example/x"
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: enviados.append((url, json)))
    s = Service(cfg)
    s.reportar("necesito el horario del gimnasio", "ip", "c")
    assert enviados and enviados[0][1]["pregunta"] == "necesito el horario del gimnasio"

    def falla(*a, **k):
        raise httpx.ConnectError("caído")
    monkeypatch.setattr(httpx, "post", falla)
    assert s.reportar("otra pregunta distinta", "ip", "c2")[0] is True  # el informe no se pierde por el webhook


def test_ejemplos_siguen_los_temas_mas_consultados(cfg):
    s = Service(cfg)
    base = s.ejemplos(4)
    assert base[0] == "¿Cuál es la dirección de la planta?"
    for _ in range(3):
        s.responder("verificacion de pulsera esd", "todos", "ip", "c")
    s.responder("contraseña", "todos", "ip", "c")
    nuevo = s.ejemplos(4)
    assert nuevo[0] == "¿Cómo verifico mi pulsera ESD?" and nuevo[1] == "Olvidé mi contraseña de sistemas"


def test_ejemplos_nunca_muestran_texto_de_usuarios(cfg):
    s = Service(cfg)
    s.responder("mi nombre es Juan Perez y quiero vacaciones", "todos", "ip", "c")
    assert all("Juan" not in e for e in s.ejemplos(10))
    assert set(s.ejemplos(10)) <= {e.pregunta for e in s.index.entries}


def test_cada_ejemplo_recupera_su_propia_entrada(cfg):
    s = Service(cfg)
    for e in s.index.entries:
        if e.pregunta:
            hits = s.index.search(e.pregunta, "todos", 1)
            assert hits and hits[0].entry.id == e.id and s._relevant(hits), e.id


def test_limite_global_usa_mensaje_propio_y_respetuoso(cfg):
    cfg.global_tokens_day = 10
    s = con_llm(cfg)
    r = s.responder(Q_LLM2, "todos", "ip", "c")
    assert r["limite"] is True and "toda la comunidad" in r["respuesta"] and "Lamentamos" in r["respuesta"]
    assert "alcanzaste tu límite" not in r["respuesta"]


def test_respuestas_directas_siguen_con_limite_agotado(cfg):
    cfg.user_queries_day = 0
    r = con_llm(cfg).responder("horario comedor", "todos", "ip", "c")
    assert r["tipo"] == "directa" and not r.get("limite")  # lo gratuito no se bloquea


def sin_llm_calls(cfg):
    calls = []
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    return Service(cfg, llm_fn=fake_llm(calls=calls)), calls


def test_enfocada_responde_solo_el_dato_y_cuesta_0(cfg):
    s, calls = sin_llm_calls(cfg)
    r = s.responder("¿A qué hora abre el comedor?", "todos", "ip", "c")
    assert r["tipo"] == "directa" and r["enfocada"] and r["entrada_id"] == "comedor" and not calls
    assert "Horario: Primer turno 11:00 a 13:30" in r["respuesta"] and "menú" not in r["respuesta"]
    assert r["fichas"][0]["id"] == "comedor"


def test_dato_no_registrado_no_se_inventa(cfg):
    r = Service(cfg).responder("teléfono del transporte", "todos", "ip", "c")
    assert "No tengo registrado: teléfono" in r["respuesta"] and "preguntar directamente" in r["respuesta"]


def test_donde_entregar_incapacidad_responde_ubicacion(cfg):
    r = Service(cfg).responder("¿Dónde entrego mi incapacidad?", "todos", "ip", "c")
    assert r["entrada_id"] == "recursos-humanos" and "Ubicación: Edificio administrativo, nivel 1" in r["respuesta"]


def test_seguimiento_usa_el_ultimo_tema(cfg):
    s = Service(cfg)
    r1 = s.responder("horario comedor", "todos", "ip", "c")
    r2 = s.responder("¿y el teléfono?", "todos", "ip", "c", previo=r1["entrada_id"])
    assert "Ext. 1500" in r2["respuesta"] and r2["entrada_id"] == "comedor"
    assert s.metrics["seguimientos"] == 1


def test_seguimiento_no_se_aplica_si_nombra_otro_tema(cfg):
    r = Service(cfg).responder("teléfono de nómina", "todos", "ip", "c", previo="comedor")
    assert r["entrada_id"] == "nomina" and "Ext. 1120" in r["respuesta"]


def test_dato_sin_tema_ni_contexto_pide_aclaracion_sin_tokens(cfg):
    s, calls = sin_llm_calls(cfg)
    r = s.responder("¿a qué hora abre?", "todos", "ip", "c")
    assert r["tipo"] == "aclaracion" and "De qué área" in r["respuesta"] and not calls and not r["fichas"]


def test_segunda_oportunidad_encuentra_cachea_y_no_cuenta_consulta(cfg):
    calls = []
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    s = Service(cfg, llm_fn=fake_llm(texto="nomina aclaracion pago", calls=calls, tin=60, tout=8))
    q = "me pagaron mal"
    assert not s._relevant(s.index.search(q, "todos", 3))  # la búsqueda local sola no la encuentra
    r = s.responder(q, "todos", "ip", "c")
    assert r["entrada_id"] == "nomina" and r["tipo"] == "directa" and len(calls) == 1
    assert s.metrics["reformuladas"] == 1 and r["uso"]["consultas"] == cfg.user_queries_day  # no gastó una consulta del día
    assert r["uso"]["tokens"] == cfg.user_tokens_day - 68
    r2 = s.responder(q, "todos", "ip", "c")
    assert r2.get("desde_cache") and len(calls) == 1


def test_reformulacion_se_recuerda_aunque_no_sirva(cfg):
    calls = []
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    s = Service(cfg, llm_fn=fake_llm(texto="zzz qqq", calls=calls))
    for _ in range(3):
        assert s.responder("cuanto cuesta un boleto de avion a Paris", "todos", "ip", "c")["tipo"] == "abstencion"
    assert len(calls) == 1  # no se vuelve a pagar la misma reformulación


def test_reformulacion_respeta_el_cupo(cfg):
    calls = []
    cfg.llm_provider, cfg.llm_api_key, cfg.user_queries_day = "anthropic", "x", 0
    s = Service(cfg, llm_fn=fake_llm(texto="nomina", calls=calls))
    assert s.responder("me pagaron mal", "todos", "ip", "c")["tipo"] == "abstencion"
    assert not calls


def _stream(deltas, usage=(700, 60), falla_al_final=False):
    def f(s, system, user, max_tokens):
        for d in deltas:
            yield "delta", d
        if falla_al_final:
            raise llm.LLMError("corte")
        yield "usage", usage
    return f


def test_streaming_emite_parciales_y_un_final(cfg):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    s = Service(cfg, stream_fn=_stream(["Entrega tu ", "solicitud en Recursos ", "Humanos [recursos-humanos]."]))
    ev = list(s.responder_stream(Q_LLM, "todos", "ip", "c"))
    kinds = [k for k, _ in ev]
    assert kinds == ["parcial", "parcial", "parcial", "final"]
    assert ev[0][1] == "Entrega tu " and ev[2][1].startswith("Entrega tu solicitud en Recursos Humanos")
    final = ev[-1][1]
    assert final["tipo"] == "llm" and final["entrada_id"] == "recursos-humanos" and final["uso"]["tokens_consulta"] == 760


def test_streaming_cortado_a_la_mitad_degrada_y_descuenta(cfg):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    s = Service(cfg, stream_fn=_stream(["Entrega tu "], falla_al_final=True))
    ev = list(s.responder_stream(Q_LLM, "todos", "ip", "c"))
    assert ev[0][0] == "parcial" and ev[-1][0] == "final"
    assert ev[-1][1]["tipo"] == "directa" and ev[-1][1]["fichas"] and "no está disponible" in " ".join(ev[-1][1]["advertencias"])
    assert s.quota.remaining("ip", "c")["tokens"] < cfg.user_tokens_day  # se descontó lo gastado


def test_respuesta_vacia_del_modelo_degrada(cfg):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"
    r = Service(cfg, stream_fn=_stream([])).responder(Q_LLM, "todos", "ip", "c")
    assert r["tipo"] == "directa"


def test_vaciar_cache_no_toca_cupos_ni_informes(cfg):
    s, _ = sin_llm_calls(cfg)
    s.responder("¿Cómo solicito mis vacaciones?", "todos", "ip", "c")
    s.reportar("algo que falta", "ip", "c")
    n = s.vaciar_cache()
    assert n == {"respuestas": 1, "reformulaciones": 0} and not s.cache and len(s.reportes) == 1
