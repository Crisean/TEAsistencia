import re

from app import ui
from app.service import Service


def test_escape_neutraliza_markdown_y_html():
    out = ui.esc("<script>alert(1)</script> **x** [a](http://x) _y_")
    assert not re.search(r"(?<!\\)<", out) and "\\*\\*x\\*\\*" in out and "\\[a\\]\\(" in out


def test_format_reply_incluye_ficha_y_fuentes(cfg):
    d = Service(cfg).responder("horario comedor", "todos", "ip", "c")
    md = ui.format_reply(d)
    assert "**Comedor**" in md and "**Horario:**" in md and "11:00 a 13:30" in md and "**Teléfono:**" in md


def test_format_reply_escapa_contenido_malicioso():
    d = {"respuesta": "<img src=x onerror=alert(1)>", "fichas": [{"titulo": "<b>T</b>", "puesto": "", "correo": "a_b@x.mx"}],
         "fuentes": [], "advertencias": ["**fuerte**"]}
    md = ui.format_reply(d)
    assert not re.search(r"(?<!\\)<", md) and "a\\_b@x.mx" in md


def test_handle_conversacion(cfg):
    hist, _, sin = ui.handle("¿Cómo solicito mis vacaciones?", [], "cid", "1.2.3.4", Service(cfg))
    assert [m["role"] for m in hist] == ["user", "assistant"] and "Recursos Humanos" in hist[1]["content"] and sin == ""


def test_handle_sin_informacion_marca_pregunta_para_informar(cfg):
    hist, _, sin = ui.handle("cuanto cuesta un boleto de avion a Paris", [], "c", "ip", Service(cfg))
    assert sin.startswith("cuanto cuesta") and "No encontré" in hist[-1]["content"]


def test_handle_vacio_no_cambia(cfg):
    base = [{"role": "assistant", "content": "x"}]
    assert ui.handle("   ", base, "c", "ip", Service(cfg)) == (base, "", "")


def test_handle_limite_de_ritmo(cfg):
    cfg.req_per_min = 2
    s = Service(cfg)
    last = []
    for _ in range(4):
        last, _, _ = ui.handle("wifi", last, "c", "ip", s)
    assert "Gracias por tu paciencia" in last[-1]["content"]


def test_handle_error_inesperado_no_se_filtra(cfg):
    s = Service(cfg)

    def roto(*a, **k):
        raise ZeroDivisionError("simulado")
        yield  # pragma: no cover

    s.responder_stream = roto
    hist, _, _ = ui.handle("wifi", [], "c", "ip", s)
    assert "Ocurrió un error" in hist[-1]["content"] and "Zero" not in hist[-1]["content"]


def _fn(demo, n_in, n_out):
    return next(f for f in demo.fns.values() if len(f.inputs) == n_in and len(f.outputs) == n_out)


def test_evento_de_envio_streaming_y_seguimiento(cfg):
    """Ejecuta el manejador real registrado en Gradio (es un generador; sin request usa IP '?')."""
    s = Service(cfg)
    demo = ui.build_ui(lambda: s)
    send = _fn(demo, 4, 8)
    ev = list(send.fn("horario del comedor", [], None, None, None))
    assert len(ev[0][0]) == 1 and ev[0][0][0]["role"] == "user"          # la pregunta aparece de inmediato
    hist, caja, _uso, cid, chips, report, sin, ent = ev[-1]
    assert [m["role"] for m in hist] == ["user", "assistant"] and "11:00 a 13:30" in hist[-1]["content"]
    assert caja == "" and cid and sin == "" and ent == "comedor"
    assert chips["visible"] is False and report["visible"] is False       # tras preguntar se ocultan los ejemplos
    h2 = list(send.fn("¿y el teléfono?", hist, cid, ent, None))[-1][0]    # seguimiento con el tema recordado
    assert "Ext. 1500" in h2[-1]["content"]
    ev3 = list(send.fn("cuanto cuesta un vuelo a Paris", h2, cid, ent, None))[-1]
    assert ev3[5]["visible"] is True and ev3[6].startswith("cuanto cuesta")  # aparece el botón de informe


def test_handle_stream_va_escribiendo_la_respuesta(cfg):
    cfg.llm_provider, cfg.llm_api_key = "anthropic", "x"

    def sf(s_, system, user, mx):
        yield "delta", "Entrega tu solicitud en "
        yield "delta", "Recursos Humanos [recursos-humanos]."
        yield "usage", (700, 60)
    s = Service(cfg, stream_fn=sf)
    ev = list(ui.handle_stream("¿Cómo entrego la solicitud de vacaciones en el edificio?", [], "c", "ip", s))
    assert [e[4] for e in ev] == [False, False, False, True]
    assert ev[1][0][-1]["content"] == "Entrega tu solicitud en "
    assert "[" not in ev[2][0][-1]["content"].replace("\\[", "")        # sin marcadores de cita a medio escribir
    assert ev[-1][3] == "recursos-humanos" and "Fuentes" not in ev[-1][0][-1]["content"]


def test_parcial_quita_marcadores_incompletos():
    assert ui._parcial("Ve a Recursos Humanos [recursos-hum") == "Ve a Recursos Humanos"
    assert ui._parcial("Dato [nomina]. Otro") == "Dato. Otro"


def test_boton_de_informe_registra_y_se_oculta(cfg):
    s = Service(cfg)
    demo = ui.build_ui(lambda: s)
    rep = _fn(demo, 3, 3)
    hist, report, sin = rep.fn("cuanto cuesta un vuelo a Paris", [], "cid", None)
    assert "Gracias" in hist[-1]["content"] and report["visible"] is False and sin == ""
    assert len(s.reportes) == 1


def test_ejemplos_cargados_al_abrir(cfg):
    s = Service(cfg)
    demo = ui.build_ui(lambda: s)
    load = next(f for f in demo.fns.values() if len(f.inputs) == 0 and len(f.outputs) == ui.N_EJEMPLOS)
    ups = load.fn()
    assert len(ups) == ui.N_EJEMPLOS and all(u["visible"] for u in ups)
    assert ups[0]["value"] == "¿Cuál es la dirección de la planta?"


def test_panel_de_informacion_oculto_y_con_datos(cfg):
    info = ui._info_md()
    assert "Latitud Oriente Sur 74" in info and "83175" in info and "maps.app.goo.gl/GTqTkmdj6zFkrEfU6" in info
    demo = ui.build_ui(lambda: Service(cfg))
    toggle = next(f for f in demo.fns.values() if len(f.inputs) == 1 and len(f.outputs) == 3)
    abre = toggle.fn(False)
    assert abre[0]["visible"] is True and abre[1] is True
    assert toggle.fn(True)[0]["visible"] is False


def test_no_se_muestran_fuentes_ni_marcadores_de_cita():
    d = {"respuesta": "Entrega tu solicitud en Recursos Humanos [1]. Lleva tu gafete [2].", "fichas": [],
         "fuentes": [{"n": 1, "id": "a", "titulo": "Recursos Humanos", "actualizado": "2026-08-15"}], "advertencias": []}
    md = ui.format_reply(d)
    assert "Fuentes" not in md and "[1]" not in md and "\\[1\\]" not in md and "[2]" not in md
    assert "Recursos Humanos" in md and "gafete" in md


def test_mensaje_de_ritmo_es_respetuoso(cfg):
    cfg.req_per_min = 1
    s = Service(cfg)
    h, _, _ = ui.handle("wifi", [], "c", "ip", s)
    h, _, _ = ui.handle("wifi", h, "c", "ip", s)
    assert "Gracias por tu paciencia" in h[-1]["content"] and "espera un minuto" in h[-1]["content"]


def test_aviso_de_limite_visible_en_la_pagina():
    assert "límite diario de consultas con IA" in ui.LEGAL


def test_css_un_solo_marco_y_sin_barra_de_herramientas():
    css = ui.CSS
    # el marco con borde naranja se aplica SOLO a .message.bot (no también a [data-testid]), para que no se dupliquen
    marcos = [ln for ln in css.splitlines() if "border-left:3px" in ln or "border-left: 3px" in ln]
    assert len(marcos) == 1 and ".message.bot" in marcos[0]
    assert "padding:14px 20px" in css and "#chat .message-content" in css
    assert ".icon-button-wrapper" in css and "display:none" in css      # sin botón de limpiar/copiar/compartir
    assert "#chat .bubble-wrap" in css and "padding:18px 16px 18px 4px" in css  # scroll separado con aire a la derecha


def _ids(demo):
    return {getattr(b, "elem_id", None) for b in demo.blocks.values()}


def test_enlace_discreto_al_panel_visible_y_desactivable(cfg, monkeypatch):
    demo = ui.build_ui(lambda: Service(cfg))
    enlace = next(b for b in demo.blocks.values() if getattr(b, "elem_id", None) == "admin-link")
    assert 'href="/admin/"' in enlace.value
    monkeypatch.setattr(ui.settings, "show_admin_link", False)
    assert "admin-link" not in _ids(ui.build_ui(lambda: Service(cfg)))


def test_cuadro_de_texto_sin_marco_naranja_al_escribir():
    css = ui.CSS
    foco = [ln for ln in css.splitlines() if "#msg:focus-within" in ln]
    assert foco and all("FF7D00" not in ln.upper() and "255,125,0" not in ln for ln in foco)   # nada naranja
    assert "#msg textarea:focus-visible" in css and "outline:none" in css                        # sin contorno del navegador
    assert "--input-shadow-focus: none" in css                                                   # sin resplandor del tema
    assert "rgba(255,255,255,.38)" in css                                                        # sigue habiendo foco visible (neutro)
