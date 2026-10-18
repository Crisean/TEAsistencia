"""Interfaz Gradio del Asistente TE: chat directo en modo oscuro con la paleta de TE Connectivity (planta Hermosillo).

Paleta del proyecto: #EEEFF0 (claro) · #39505F (pizarra) · #08090B (casi negro) · #2E4956 (petróleo) · #65899F (acero),
más el naranja de la marca TE (#EB8002, tomado del logotipo) como acento.
Derivados para el modo oscuro: fondo #08090B y superficies #11171B/#1A252C (tonos oscuros de #2E4956).
Contraste: texto #EEEFF0 sobre fondo (>17:1), burbuja del usuario blanco sobre #2E4956/#39505F (≥8:1),
flecha de envío #08090B sobre naranja (≈7:1). Los enlaces usan un tinte claro de #65899F (#9DBBCD, ≥8:1).
"""
from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable

import gradio as gr

from .config import BASE, settings

log = logging.getLogger("asistente_te")

ORANGE, ORANGE2 = "#EB8002", "#F59B2E"
INKD, SLATE, TEAL, STEEL = "#08090B", "#39505F", "#2E4956", "#65899F"
GRAY, SOFT, WHITE = "#9AA7B0", "#EEEFF0", "#FFFFFF"
BG, SURFACE, SURFACE2, LINE, LINK = "#08090B", "#11171B", "#1A252C", "rgba(238,239,240,.10)", "#9DBBCD"

NOMBRE = settings.app_name
SALUDO = (f"Hola, soy el **{NOMBRE}**. Pregúntame por documentación, procedimientos, áreas de la planta "
          "o a quién acudir, y te respondo al instante.")
LEGAL = (f"El {NOMBRE} es una guía interna de apoyo: confirma lo importante con el área responsable y consulta siempre "
         "la versión vigente del documento controlado. Tus preguntas se procesan con un servicio de IA de un tercero; "
         "no escribas datos personales, de salud ni información confidencial de clientes o productos. "
         "Cada persona tiene un límite diario de consultas con IA. En una emergencia sigue el plan de emergencia de la planta.")
MSG_RITMO = ("Estás enviando consultas muy rápido. Para que el servicio funcione bien para todas las personas, "
             "espera un minuto antes de continuar. ¡Gracias por tu paciencia!")
INFO_FALLBACK = "**TE CONNECTIVITY · Data & Devices**\nPlanta Hermosillo, Sonora"
N_EJEMPLOS = 4


def _both(d: dict) -> dict:
    """El tema oscuro se aplica igual en claro y oscuro: si el navegador no activara .dark, nada queda ilegible."""
    return {**d, **{k + "_dark": v for k, v in d.items()}}


THEME = gr.themes.Base(
    font=["Inter", "system-ui", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
    radius_size=gr.themes.sizes.radius_lg,
).set(**_both({
    "body_background_fill": BG, "body_text_color": SOFT, "body_text_color_subdued": GRAY,
    "background_fill_primary": BG, "background_fill_secondary": SURFACE,
    "block_background_fill": "transparent", "block_border_color": "transparent", "block_border_width": "0px",
    "block_shadow": "none", "block_label_text_color": GRAY, "block_title_text_color": SOFT,
    "panel_background_fill": SURFACE, "border_color_primary": "rgba(255,255,255,.10)",
    "input_background_fill": SURFACE, "input_border_color": "rgba(255,255,255,.10)", "input_border_color_focus": ORANGE2,
    "input_placeholder_color": GRAY,
    "button_primary_background_fill": ORANGE, "button_primary_background_fill_hover": ORANGE2,
    "button_primary_text_color": INKD, "button_primary_border_color": ORANGE,
    "button_secondary_background_fill": SURFACE, "button_secondary_background_fill_hover": SURFACE2,
    "button_secondary_text_color": SOFT, "button_secondary_border_color": "rgba(255,255,255,.10)",
    "link_text_color": LINK,
}))

CSS = f"""
body, .gradio-container {{
  background: radial-gradient(900px 480px at 0% -8%, rgba(46,73,86,.55), transparent 60%),
              radial-gradient(700px 420px at 100% -5%, rgba(235,128,2,.12), transparent 60%), {BG} !important; }}
.gradio-container {{ max-width: 760px !important; margin: 0 auto !important; padding: 0 12px !important; }}
footer {{ display:none !important; }}

#top {{ align-items:center !important; flex-wrap:nowrap !important; gap:.5rem; padding:.9rem 0 .8rem; position:relative;
  border-bottom:1px solid {LINE}; }}
#top::after {{ content:""; position:absolute; left:0; bottom:-1px; width:104px; height:2px;
  background:linear-gradient(90deg,{ORANGE},{ORANGE2}); }}
#brand {{ display:flex; align-items:center; gap:.9rem; }}
#brand img {{ height:44px; width:auto; }}
#brand .t {{ display:flex; flex-direction:column; line-height:1.15; padding-left:.9rem; border-left:1px solid {LINE}; }}
#brand .t b {{ font-size:1.3rem; letter-spacing:.09em; color:{SOFT}; }}
#brand .t b i {{ font-style:normal; color:{ORANGE2}; }}
#brand .t span {{ font-size:.8rem; color:{GRAY}; }}

#info-btn {{ flex:0 0 40px !important; min-width:40px !important; width:40px !important; height:40px; padding:0 !important;
  border-radius:50% !important; background:transparent !important; color:{SOFT} !important;
  border:1px solid rgba(255,255,255,.25) !important; font:italic 700 1.05rem Georgia, serif !important; }}
#info-btn:hover {{ border-color:{ORANGE2} !important; color:{ORANGE2} !important; }}
#info-panel {{ position:fixed; top:74px; right:14px; z-index:100; width:min(92vw,340px); padding:1rem 1.15rem !important;
  background:{SURFACE2} !important; border:1px solid rgba(255,255,255,.14) !important; border-radius:16px;
  box-shadow:0 18px 50px rgba(0,0,0,.6); }}
#info-panel, #info-panel * {{ color:{SOFT}; font-size:.92rem; line-height:1.5; }}
#info-panel a {{ color:{LINK}; }}

#chat {{ border:0 !important; background:transparent !important; }}
/* El scroll del chat vive en .bubble-wrap: se le da aire a la derecha y una barra fina y discreta. */
#chat .bubble-wrap {{ padding:18px 16px 18px 4px !important; scrollbar-width:thin; scrollbar-color:{TEAL} transparent; }}
#chat .bubble-wrap::-webkit-scrollbar {{ width:8px; }}
#chat .bubble-wrap::-webkit-scrollbar-track {{ background:transparent; }}
#chat .bubble-wrap::-webkit-scrollbar-thumb {{ background:{TEAL}; border-radius:8px; }}
/* Sin barra de herramientas del chat (limpiar / copiar todo / compartir): cada visita ya es una conversación nueva. */
#chat .icon-button-wrapper, #chat .icon-buttons {{ display:none !important; }}
#chat .message-buttons {{ display:none !important; }}

/* UN solo marco por mensaje (.message.bot / .message.user) con relleno propio: el marco queda más grande que el texto.
   El elemento interior [data-testid] y .message-content NO llevan borde, fondo ni relleno, para que no se dupliquen. */
#chat .message.bot, #chat .message.user {{ padding:14px 20px !important; line-height:1.6; }}
#chat .message.bot {{ background:{SURFACE} !important; border:1px solid {LINE} !important; border-left:3px solid {ORANGE2} !important;
  border-radius:6px 20px 20px 20px !important; box-shadow:none !important; }}
#chat .message.user {{ background:linear-gradient(135deg,{TEAL},{SLATE}) !important; border:0 !important;
  border-radius:20px 20px 6px 20px !important; box-shadow:none !important; }}
#chat [data-testid="bot"], #chat [data-testid="user"] {{ background:transparent !important; border:0 !important; box-shadow:none !important;
  padding:0 !important; margin:0 !important; border-radius:0 !important; }}
#chat .message-content {{ padding:0 !important; min-height:0 !important; }}
#chat .message.bot, #chat .message.bot * {{ color:{SOFT}; }}
#chat .message.bot strong {{ color:{WHITE}; }}
#chat .message.user, #chat .message.user * {{ color:{WHITE} !important; }}
#chat .message p {{ margin:.35rem 0 !important; }}
#chat .message ul {{ margin:.35rem 0 !important; padding-left:1.1rem; }}
#chat a {{ color:{LINK} !important; }}

#chips {{ flex-wrap:wrap !important; gap:.5rem !important; }}
.chip {{ flex:0 1 auto !important; min-width:0 !important; border-radius:999px !important; background:rgba(255,255,255,.04) !important;
  border:1px solid rgba(255,255,255,.16) !important; color:{SOFT} !important; font-size:.9rem !important; padding:.45rem .95rem !important; }}
.chip:hover {{ border-color:{ORANGE2} !important; background:rgba(235,128,2,.10) !important; }}

#report-row {{ align-items:center !important; gap:.75rem; }}
#report-btn {{ flex:0 0 auto !important; border-radius:999px !important; background:transparent !important; color:{ORANGE2} !important;
  border:1px solid {ORANGE2} !important; font-size:.9rem !important; }}
#report-btn:hover {{ background:rgba(235,128,2,.12) !important; }}
#report-note {{ font-size:.8rem; color:{GRAY}; }}

#msg {{ background:{SURFACE} !important; border:1px solid rgba(255,255,255,.14) !important; border-radius:28px !important; padding:.25rem .4rem .25rem 1rem !important; }}
#msg {{ --input-border-color-focus: rgba(255,255,255,.38); --input-shadow-focus: none; }}
/* Sin marco naranja al escribir: el único indicador de foco es un borde blanco más claro (accesible, discreto). */
#msg:focus-within {{ border-color:rgba(255,255,255,.38) !important; box-shadow:none !important; }}
#msg textarea:focus, #msg textarea:focus-visible {{ outline:none !important; box-shadow:none !important; border:0 !important; }}
#msg button:focus-visible {{ outline:2px solid {SOFT} !important; outline-offset:2px; }}
#msg textarea {{ background:transparent !important; border:0 !important; box-shadow:none !important; color:{SOFT} !important; font-size:1.02rem; }}
#msg button {{ background:linear-gradient(135deg,{ORANGE},{ORANGE2}) !important; color:{INKD} !important; border:0 !important;
  border-radius:50% !important; min-width:42px; min-height:42px; }}
#msg button svg {{ color:{INKD} !important; fill:{INKD} !important; stroke:{INKD} !important; }}

#admin-link {{ text-align:center; font-size:.75rem; padding-bottom:.6rem; }}
#admin-link a {{ color:{GRAY}; text-decoration:none; }}
#admin-link a:hover {{ color:{ORANGE2}; text-decoration:underline; }}
#uso, #legal {{ font-size:.78rem; color:{GRAY}; text-align:center; }}
#uso p, #legal p {{ color:{GRAY}; margin:.15rem 0; }}
button:focus-visible, textarea:focus-visible, a:focus-visible {{ outline:3px solid {ORANGE2} !important; outline-offset:2px; }}
@media (max-width: 520px) {{ #brand img {{ height:34px; }} #brand .t b {{ font-size:1.05rem; }} #brand .t span {{ display:none; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ animation:none !important; transition:none !important; }} }}
"""

JS = """() => {
  document.documentElement.lang = 'es';
  document.body.classList.add('dark');
  const label = (sel, text) => { const t = setInterval(() => { const e = document.querySelector(sel);
    if (e) { e.setAttribute('aria-label', text); clearInterval(t); } }, 300); setTimeout(() => clearInterval(t), 8000); };
  label('#info-btn', 'Información de la planta');
  label('#msg button', 'Enviar pregunta');
}"""

_MD = re.compile(r"([\\`*_{}\[\]<>()#+!|~])")


def esc(s: str) -> str:
    """Escapa caracteres de Markdown/HTML: el contenido del corpus se muestra como texto, nunca como formato."""
    return _MD.sub(r"\\\1", s or "")


def format_reply(d: dict) -> str:
    """Convierte la respuesta del servicio en Markdown seguro."""
    texto = re.sub(r"\s*\[\d+\]", "", d.get("respuesta", ""))  # marcadores de cita internos: no se muestran
    parts = [esc(texto).replace("\n", "  \n")]
    for a in d.get("advertencias", []):
        parts.append(f"**Aviso:** {esc(a)}")
    for f in d.get("fichas", []):
        head = f"**{esc(f['titulo'])}**" + (f" — {esc(f['puesto'])}" if f.get("puesto") else "")
        rows = [("Responsable", f.get("responsable")), ("Ubicación", f.get("ubicacion")), ("Horario", f.get("horario")),
                ("Teléfono", f.get("telefono")), ("Correo", f.get("correo")), ("Web", f.get("web")),
                ("Actualizado", f.get("actualizado"))]
        lines = [f"- **{k}:** {esc(v)}" for k, v in rows if v]
        if f.get("desactualizado"):
            lines.append("- **Aviso:** esta información puede estar desactualizada; confirma con el área responsable.")
        parts.append(head + "\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _parcial(texto: str) -> str:
    """Texto a medio escribir: sin marcadores de cita (completos o incompletos) y escapado."""
    return esc(re.sub(r"\s*\[[a-z0-9\-]*(\]|$)", "", texto))


def handle_stream(msg: str, history: list, cid: str, ip: str, service, previo: str | None = None):
    """Lógica del chat como generador (se prueba sin navegador).

    Emite tuplas (historial, texto de uso, pregunta sin respuesta, último tema, es_final). La pregunta del usuario
    aparece de inmediato y la respuesta se va escribiendo; la última tupla (es_final=True) trae la respuesta completa.
    """
    history = list(history or [])
    msg = " ".join((msg or "").split())[: settings.max_query_chars]
    if not msg:
        yield history, "", "", previo, True
        return
    base = history + [{"role": "user", "content": msg}]
    yield base, "", "", previo, False
    sin, uso, entrada = "", "", previo
    if not service.quota.rate_ok(ip, cid):
        reply = MSG_RITMO
    else:
        try:
            final = {}
            for kind, val in service.responder_stream(msg, "todos", ip, cid, previo):
                if kind == "parcial":
                    yield base + [{"role": "assistant", "content": _parcial(val)}], "", "", previo, False
                else:
                    final = val
            reply = format_reply(final)
            r = final.get("uso", {})
            uso = f"Consultas con IA restantes hoy: {r['consultas']}" if "consultas" in r else ""
            sin = msg if final.get("tipo") == "abstencion" else ""
            entrada = final.get("entrada_id") or previo
        except Exception:  # nunca mostrar un error técnico al usuario
            log.exception("error inesperado en el chat")
            reply = "Ocurrió un error. Inténtalo de nuevo en un momento."
    yield base + [{"role": "assistant", "content": reply}], uso, sin, entrada, True


def handle(msg: str, history: list, cid: str, ip: str, service, previo: str | None = None) -> tuple[list, str, str]:
    """Versión sin streaming: devuelve (historial, texto de uso, pregunta sin respuesta)."""
    ultimo = None
    for ultimo in handle_stream(msg, history, cid, ip, service, previo):
        pass
    return ultimo[0], ultimo[1], ultimo[2]


def client_ip(request) -> str:
    if request is None:
        return "?"
    xff = request.headers.get("x-forwarded-for", "") if request.headers else ""
    return (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "?"))[:64]


def _info_md() -> str:
    p = BASE / "data" / "info_planta.md"
    return p.read_text("utf-8") if p.exists() else INFO_FALLBACK


def build_ui(get_service: Callable[[], object]) -> gr.Blocks:
    with gr.Blocks(title=f"{NOMBRE} · TE Connectivity Hermosillo", analytics_enabled=False) as demo:
        with gr.Row(elem_id="top"):
            gr.HTML('<div id="brand"><img src="/static/logo_dark.png" alt="TE Connectivity">'
                    '<div class="t"><b>ASISTENTE <i>INTERNO</i></b>'
                    '<span>Documentación, respuestas rápidas y áreas de la planta</span></div></div>')
            info_btn = gr.Button("i", elem_id="info-btn", scale=0)
        with gr.Column(visible=False, elem_id="info-panel") as info_panel:
            gr.Markdown(_info_md())

        chat = gr.Chatbot(value=[{"role": "assistant", "content": SALUDO}], elem_id="chat", height="56vh",
                          show_label=False, label="Conversación", buttons=[])
        with gr.Row(elem_id="chips") as chips:
            ejemplos = [gr.Button("", elem_classes="chip", visible=False, size="sm") for _ in range(N_EJEMPLOS)]
        with gr.Row(visible=False, elem_id="report-row") as report_row:
            report_btn = gr.Button("Informar que falta esta información", elem_id="report-btn", size="sm", scale=0)
            gr.Markdown("Se envía solo tu pregunta, sin datos personales.", elem_id="report-note")
        msg = gr.Textbox(elem_id="msg", container=False, show_label=False, label="Tu pregunta", lines=1, max_lines=4,
                         placeholder="Ej.: ¿dónde está Calidad? · procedimiento de ESD…", max_length=settings.max_query_chars, submit_btn=True,
                         autofocus=True)
        uso = gr.Markdown("", elem_id="uso")
        gr.Markdown(LEGAL, elem_id="legal")
        if settings.show_admin_link:
            gr.HTML('<a href="/admin/">Administración</a>', elem_id="admin-link")

        cid_state = gr.BrowserState(None)  # id anónimo (solo para los cupos de uso); la conversación NO se guarda
        sin_state = gr.State("")
        prev_state = gr.State(None)  # último tema consultado en ESTA conversación (se pierde al recargar)
        open_state = gr.State(False)

        def on_send(text, history, cid, previo, request: gr.Request):
            cid = cid or uuid.uuid4().hex
            n0 = len(history or [])
            for h, u, sin, ent, final in handle_stream(text, history, cid, client_ip(request), get_service(), previo):
                oculta = gr.update(visible=False) if len(h) > n0 else gr.update()
                if final:
                    yield (h, "", u, cid, oculta, gr.update(visible=bool(sin)), sin, ent)
                else:
                    yield (h, "", gr.update(), cid, oculta, gr.update(), gr.update(), gr.update())

        ins = [msg, chat, cid_state, prev_state]
        outs = [chat, msg, uso, cid_state, chips, report_row, sin_state, prev_state]
        msg.submit(on_send, ins, outs, api_name=False, concurrency_limit=8)
        for b in ejemplos:  # el valor del botón es la pregunta modelo
            b.click(on_send, [b, chat, cid_state, prev_state], outs, api_name=False, concurrency_limit=8)

        def on_report(sin, history, cid, request: gr.Request):
            _ok, texto = get_service().reportar(sin, client_ip(request), cid or "anon")
            history = list(history or []) + [{"role": "assistant", "content": esc(texto)}]
            return history, gr.update(visible=False), ""

        report_btn.click(on_report, [sin_state, chat, cid_state], [chat, report_row, sin_state], api_name=False)

        def on_info(opened):
            return gr.update(visible=not opened), not opened, gr.update(value="✕" if not opened else "i")

        info_btn.click(on_info, [open_state], [info_panel, open_state, info_btn], api_name=False)

        def cargar_ejemplos():  # se ejecuta en cada visita: siempre una conversación nueva y ejemplos actualizados
            ej = get_service().ejemplos(N_EJEMPLOS)
            return [gr.update(value=ej[i], visible=True) if i < len(ej) else gr.update(visible=False)
                    for i in range(N_EJEMPLOS)]

        demo.load(cargar_ejemplos, None, ejemplos, api_name=False)
        demo.queue(max_size=32)
    return demo
