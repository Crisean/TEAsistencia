"""Panel web de administración (/admin): resumen, edición del corpus, importación con IA y borradores desde informes.

Seguridad: toda acción exige el ADMIN_TOKEN (se vuelve a comprobar en CADA llamada, no solo al entrar) y hay bloqueo
tras 5 intentos fallidos en 10 minutos. Publicar en GitHub usa un token propio con permiso SOLO sobre este repositorio.
"""
from __future__ import annotations

import base64
import hmac
import logging
import os
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlparse

import gradio as gr
import httpx

from . import admin_ai, llm
from .config import Settings, settings
from .corpus import parse_corpus
from .index import corpus_hash
from .ui import esc

log = logging.getLogger("asistente_te")
MAX_CORPUS_CHARS = 400_000

ADMIN_CSS = """
.gradio-container { max-width: 1000px !important; }
#editor textarea, #propuesta textarea, #propuesta2 textarea { font-family: ui-monospace, Menlo, Consolas, monospace !important; font-size: .85rem !important; }
#admin-title { font-size:1.15rem; letter-spacing:.06em; color:#EEEFF0; padding:.9rem 0 .5rem; border-bottom:1px solid rgba(238,239,240,.1); }
#admin-title b { color:#EB8002; }
"""


def publicar_github(texto: str, s: Settings) -> str:
    """Guarda el corpus en GitHub (commit en la rama configurada). Render redespliega solo si autoDeploy está activo."""
    if not (s.github_token and s.github_repo):
        return ("GitHub no está configurado (GITHUB_TOKEN y GITHUB_REPO): el cambio quedó solo en el servidor y "
                "se perderá al reiniciar.")
    url = f"https://api.github.com/repos/{s.github_repo}/contents/{s.github_corpus_path}"
    h = {"Authorization": f"Bearer {s.github_token}", "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    try:
        r = httpx.get(url, headers=h, params={"ref": s.github_branch}, timeout=15)
        sha = r.json().get("sha") if r.status_code == 200 else None
        if r.status_code not in (200, 404):
            return f"No se pudo leer el archivo en GitHub (HTTP {r.status_code}). Revisa GITHUB_TOKEN, GITHUB_REPO y la rama."
        body = {"message": "Actualiza el corpus desde el panel de administración",
                "content": base64.b64encode(texto.encode("utf-8")).decode(), "branch": s.github_branch}
        if sha:
            body["sha"] = sha
        r = httpx.put(url, headers=h, json=body, timeout=20)
        if r.status_code not in (200, 201):
            return f"GitHub rechazó el cambio (HTTP {r.status_code}). Verifica que el token tenga permiso de escritura (Contents)."
        return f"Publicado en GitHub (commit {r.json()['commit']['sha'][:7]}). Render redesplegará en unos minutos."
    except (httpx.HTTPError, KeyError, ValueError):
        return "No se pudo conectar con GitHub; el cambio quedó solo en el servidor y se perderá al reiniciar."


class Admin:
    def __init__(self, get_service: Callable, s: Settings = settings):
        self.get_service, self.s = get_service, s
        self._fails: dict[str, deque] = defaultdict(deque)

    def guard(self, token: str, ip: str) -> None:
        now, q = time.time(), self._fails[ip]
        while q and now - q[0] > 600:
            q.popleft()
        if len(q) >= 5:
            raise PermissionError("Demasiados intentos. Espera unos minutos.")
        if not self.s.admin_token:
            raise PermissionError("Administración deshabilitada: falta definir ADMIN_TOKEN.")
        if not hmac.compare_digest((token or "").encode(), self.s.admin_token.encode()):
            q.append(now)
            raise PermissionError("Token inválido.")

    # ---------- lectura ----------
    def resumen(self, token: str, ip: str) -> str:
        self.guard(token, ip)
        sv = self.get_service()
        est = sv.estado()
        titulos = {e.id: e.titulo for e in sv.index.entries}
        m = est["metricas"]
        out = [(f"**Entradas:** {est['entradas']} · **IA configurada:** {'sí' if est['llm_configurado'] else 'no'} · "
               f"**Caché:** {est['cache']} · **Tokens usados hoy:** {est['cuotas']['tokens_globales']} de {est['cuotas']['tope_global']}"),
               "", (f"**Consultas:** {m.get('consultas', 0)} · directas {m.get('directas', 0)} · enfocadas {m.get('enfocadas', 0)} · "
               f"seguimientos {m.get('seguimientos', 0)} · con IA {m.get('llm', 0)} · reformuladas {m.get('reformuladas', 0)} · "
               f"sin respuesta {m.get('abstenciones', 0)} · informes {m.get('reportes', 0)}"), "", "### Temas más consultados"]
        pop = sv.popularidad.most_common(8)
        out += [f"- {esc(titulos.get(i, i))}: {n}" for i, n in pop] or ["- (aún sin datos)"]
        out += ["", "### Informes de «sin respuesta» (más frecuentes primero)"]
        reps = sorted(sv.reportes.values(), key=lambda r: -r["veces"])[:15]
        out += [f"- {esc(r['pregunta'])} — {r['veces']} vez/veces ({r['fecha']})" for r in reps] or ["- (ninguno)"]
        if est["desactualizadas"]:
            out += ["", "### Fichas desactualizadas", *[f"- {esc(titulos.get(i, i))}" for i in est["desactualizadas"]]]
        if est["problemas"]:
            out += ["", "### Avisos del corpus", *[f"- {esc(p)}" for p in est["problemas"][:15]]]
        return "\n".join(out)

    def cargar(self, token: str, ip: str) -> str:
        self.guard(token, ip)
        p = self.s.corpus_path
        return p.read_text("utf-8") if p.exists() else ""

    # ---------- edición ----------
    def validar(self, texto: str, token: str, ip: str) -> str:
        self.guard(token, ip)
        entradas, problemas = parse_corpus(texto or "")
        errores = [p for p in problemas if p.level == "error"]
        lineas = [f"**{len(entradas)} fichas válidas · {len(errores)} errores · {len(problemas) - len(errores)} avisos**"]
        lineas += [f"- {esc(str(p))}" for p in problemas[:40]]
        return "\n".join(lineas)

    def guardar(self, texto: str, token: str, ip: str) -> str:
        self.guard(token, ip)
        texto = (texto or "").replace("\r\n", "\n")
        if len(texto) > MAX_CORPUS_CHARS:
            return "No se guardó: el corpus supera el tamaño máximo."
        entradas, problemas = parse_corpus(texto)
        errores = [p for p in problemas if p.level == "error"]
        if errores:
            return "**No se guardó.** Corrige primero:\n" + "\n".join(f"- {esc(str(p))}" for p in errores[:20])
        ruta = self.s.corpus_path
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(texto, "utf-8")
        tmp.replace(ruta)
        self.get_service().reindex()
        log.info("corpus actualizado desde el panel: %d entradas", len(entradas))
        return f"Guardado y aplicado ahora ({len(entradas)} fichas). {publicar_github(texto, self.s)}"

    # ---------- memoria y configuración ----------
    def _fecha(self, ts: float) -> str:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self.s.timezone)
        except (ImportError, KeyError, ValueError, OSError):
            tz = UTC
        return datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M")

    def memoria(self, token: str, ip: str) -> str:
        """Estado de lo que el servicio tiene cargado en memoria frente al archivo del catálogo."""
        self.guard(token, ip)
        sv, idx, s = self.get_service(), self.get_service().index, self.s
        ruta, sin = s.corpus_path, s.synonyms_path
        texto = ruta.read_text("utf-8") if ruta.exists() else ""
        syn = sin.read_text("utf-8") if sin.exists() else ""
        al_dia = corpus_hash(texto, syn) == idx.chash
        estado = ("**al día**: el índice coincide con el archivo." if al_dia else
                  "**desactualizado**: el archivo cambió desde la última indexación. Pulsa «Reindexar ahora».")
        lin = [f"**Índice:** {len(idx.entries)} fichas · huella `{idx.chash[:12]}` · indexado {self._fecha(idx.built_at)}",
               f"**Archivo `{esc(ruta.name)}`:** modificado {self._fecha(ruta.stat().st_mtime) if ruta.exists() else 'no existe'}",
               f"**Estado:** {estado}", "",
               (f"**Caché de respuestas:** {len(sv.cache)} de {s.cache_size} · **Reformulaciones guardadas:** {len(sv._reform)} · "
               f"**Informes pendientes:** {len(sv.reportes)}"),
               f"**Consultas desde el último arranque:** {sv.metrics.get('consultas', 0)}", "",
               ("*Todo esto vive en la memoria del servidor y se reinicia cuando Render reinicia el servicio. "
               "Vaciar la caché no reinicia los cupos de los usuarios.*")]
        return "\n".join(lin)

    def reindexar(self, token: str, ip: str) -> str:
        self.guard(token, ip)
        est = self.get_service().reindex()
        log.info("reindexado manual desde el panel: %d entradas", est["entradas"])
        return (f"Índice reconstruido desde `{esc(self.s.corpus_path.name)}`: {est['entradas']} fichas y "
                f"{len(est['problemas'])} avisos. La caché se vació.")

    def vaciar_cache(self, token: str, ip: str) -> str:
        self.guard(token, ip)
        n = self.get_service().vaciar_cache()
        return f"Caché vaciada: {n['respuestas']} respuestas y {n['reformulaciones']} reformulaciones. Las próximas consultas se recalculan."

    def configuracion(self, token: str, ip: str) -> str:
        """Muestra la configuración activa SIN revelar secretos (solo si están configurados o no)."""
        self.guard(token, ip)
        s, sv = self.s, self.get_service()

        def cfg(v: bool) -> str:
            return "configurado" if v else "no configurado"
        host = urlparse(s.llm_base_url).netloc if s.llm_base_url else "(por defecto del proveedor)"
        grupos = {
            "Modelo de IA": [("LLM_PROVIDER", s.llm_provider), ("MODEL_NAME", s.model_name), ("LLM_API_KEY", cfg(s.llm_api_key)),
                             ("LLM_BASE_URL (host)", host), ("LLM_TIMEOUT_S", s.llm_timeout_s)],
            "Límites por consulta": [("MAX_QUERY_CHARS", s.max_query_chars), ("TOP_K", s.top_k),
                                     ("MAX_CONTEXT_CHARS", s.max_context_chars), ("MAX_OUTPUT_TOKENS", s.max_output_tokens)],
            "Cupos": [("USER_TOKENS_DAY", s.user_tokens_day), ("USER_QUERIES_DAY", s.user_queries_day),
                      ("REQ_PER_MIN", s.req_per_min), ("IP_MULTIPLIER", s.ip_multiplier),
                      ("GLOBAL_TOKENS_DAY", s.global_tokens_day), ("REPORTS_PER_DAY", s.reports_per_day)],
            "Recuperación y caché": [("MIN_SCORE", s.min_score), ("MIN_COVERAGE", s.min_coverage),
                                     ("DIRECT_ENABLED", s.direct_enabled), ("DIRECT_COVERAGE", s.direct_coverage),
                                     ("DIRECT_RATIO", s.direct_ratio), ("STALE_DAYS", s.stale_days),
                                     ("CACHE_SIZE", s.cache_size), ("CACHE_TTL_S", s.cache_ttl_s)],
            "Importación con IA": [("IMPORT_MAX_CHUNKS", s.import_max_chunks), ("IMPORT_CHUNK_CHARS", s.import_chunk_chars)],
            "Publicación en GitHub": [("GITHUB_TOKEN", cfg(s.github_token)), ("GITHUB_REPO", s.github_repo or "(vacío)"),
                                      ("GITHUB_BRANCH", s.github_branch), ("GITHUB_CORPUS_PATH", s.github_corpus_path)],
            "Servicio": [("ADMIN_TOKEN", cfg(s.admin_token)), ("ID_SALT", "valor por defecto" if s.id_salt == "cambia-esto" else "personalizada"),
                         ("TIMEZONE", s.timezone), ("REPORT_WEBHOOK_URL", cfg(s.report_webhook_url)),
                         ("SHOW_ADMIN_LINK", s.show_admin_link), ("Catálogo", s.corpus_path.name)],
        }
        avisos = []
        if not s.llm_api_key and s.llm_provider != "none":
            avisos.append("`LLM_API_KEY` no está configurada: solo funcionan las respuestas directas.")
        if s.id_salt == "cambia-esto":
            avisos.append("`ID_SALT` usa el valor por defecto: define una cadena aleatoria propia.")
        if len(s.admin_token) < 16:
            avisos.append("`ADMIN_TOKEN` es corto: usa al menos 16 caracteres aleatorios.")
        if not (s.github_token and s.github_repo):
            avisos.append("GitHub no está configurado: los cambios del panel se perderán al reiniciar el servicio.")
        out = []
        if avisos:
            out += ["### Recomendaciones", *[f"- {a}" for a in avisos], ""]
        for titulo, filas in grupos.items():
            out += [f"### {titulo}", "| Variable | Valor |", "|---|---|", *[f"| `{k}` | {esc(str(v))} |" for k, v in filas], ""]
        out.append(f"*{len(sv.index.entries)} fichas cargadas. Para cambiar estos valores edita las variables de entorno en Render "
                   "(Environment) y redespliega: este panel solo los muestra. Los secretos nunca se muestran.*")
        return "\n".join(out)

    # ---------- IA (solo administrador) ----------
    def importar(self, ruta: str | None, token: str, ip: str) -> tuple[str, str]:
        self.guard(token, ip)
        if not ruta:
            return "", "Sube un archivo primero."
        if not llm.available(self.s):
            return "", "Configura LLM_API_KEY para usar la IA."
        try:
            with open(ruta, "rb") as f:
                data = f.read(admin_ai.MAX_BYTES + 1)
            texto = admin_ai.extraer_texto(os.path.basename(ruta), data)
        except (OSError, ValueError) as e:
            return "", f"No se pudo leer el archivo: {esc(str(e))}"
        existentes = {e.id for e in self.get_service().index.entries}
        try:
            prop, res = admin_ai.importar_texto(texto, os.path.basename(ruta), llm.complete, self.s, existentes)
        except llm.LLMError as e:
            return "", f"Falló la llamada a la IA ({esc(str(e))})."
        return prop, self._res_md(res)

    def borrador(self, token: str, ip: str) -> tuple[str, str]:
        self.guard(token, ip)
        if not llm.available(self.s):
            return "", "Configura LLM_API_KEY para usar la IA."
        sv = self.get_service()
        try:
            prop, res = admin_ai.borrador_desde_reportes(list(sv.reportes.values()), llm.complete, self.s,
                                                         {e.id for e in sv.index.entries})
        except ValueError as e:
            return "", esc(str(e))
        except llm.LLMError as e:
            return "", f"Falló la llamada a la IA ({esc(str(e))})."
        return prop, self._res_md(res)

    @staticmethod
    def _res_md(res: dict) -> str:
        lin = [(f"**{res['fichas']} fichas propuestas** · fragmentos: {res['fragmentos']} · "
             f"tokens: {res['tokens_entrada']} entrada + {res['tokens_salida']} salida")]
        lin += [f"- {esc(a)}" for a in res["avisos"]]
        lin.append("Revisa y edita la propuesta; luego «Agregar al editor» y «Guardar y publicar» en la pestaña Corpus.")
        return "\n".join(lin)


def _ip(request) -> str:
    from .ui import client_ip
    return client_ip(request)


def build_admin_ui(get_service: Callable, s: Settings = settings) -> gr.Blocks:
    ad = Admin(get_service, s)

    def seguro(fn, *args, request: gr.Request):
        try:
            return fn(*args, _ip(request))
        except PermissionError as e:
            raise gr.Error(str(e)) from e

    with gr.Blocks(title=f"{settings.app_name} · Administración", analytics_enabled=False) as demo:
        gr.HTML(f'<div id="admin-title"><b>{settings.app_name.upper()}</b> · Administración</div>')
        token_state = gr.State("")
        with gr.Column() as login_box:
            tok = gr.Textbox(label="Token de administración", type="password", max_length=200)
            entrar = gr.Button("Entrar", variant="primary")
            msg = gr.Markdown("")
        with gr.Column(visible=False) as panel, gr.Tabs():
            with gr.Tab("Resumen"):
                refrescar = gr.Button("Actualizar", size="sm")
                resumen_md = gr.Markdown()
            with gr.Tab("Corpus"):
                editor = gr.Textbox(label="data/corpus.txt", lines=22, max_lines=45, elem_id="editor")
                with gr.Row():
                    b_cargar = gr.Button("Recargar el actual", size="sm")
                    b_validar = gr.Button("Validar", size="sm")
                    b_guardar = gr.Button("Guardar y publicar", variant="primary", size="sm")
                estado = gr.Markdown()
            with gr.Tab("Memoria"):
                gr.Markdown("Lo que el servicio tiene cargado ahora. **Guardar y publicar** ya reindexa solo; usa estos botones "
                            "si editaste el archivo por otra vía o quieres forzar un recálculo.")
                memoria_md = gr.Markdown()
                with gr.Row():
                    b_mem = gr.Button("Actualizar estado", size="sm")
                    b_reidx = gr.Button("Reindexar ahora", variant="primary", size="sm")
                    b_cache = gr.Button("Vaciar caché", size="sm")
                estado_mem = gr.Markdown()
            with gr.Tab("Importar con IA"):
                gr.Markdown("Sube un reglamento, convocatoria o página guardada (PDF, HTML, TXT o MD, máx. 3 MB). "
                            "La IA propone fichas; **tú revisas** antes de publicar. Usa tokens una sola vez por documento.")
                archivo = gr.File(label="Documento", file_types=[".pdf", ".txt", ".md", ".html", ".htm"], type="filepath")
                b_imp = gr.Button("Generar propuesta (usa IA)", variant="primary", size="sm")
                prop1 = gr.Textbox(label="Propuesta (editable)", lines=14, max_lines=40, elem_id="propuesta")
                res1 = gr.Markdown()
                add1 = gr.Button("Agregar al editor del corpus", size="sm")
            with gr.Tab("Borrador desde informes"):
                gr.Markdown("Convierte las preguntas sin respuesta más frecuentes en fichas **borrador** con "
                            "`[COMPLETAR]`. No se pueden publicar hasta que escribas la información oficial.")
                b_bor = gr.Button("Generar borrador (usa IA)", variant="primary", size="sm")
                prop2 = gr.Textbox(label="Borrador (editable)", lines=12, max_lines=40, elem_id="propuesta2")
                res2 = gr.Markdown()
                add2 = gr.Button("Agregar al editor del corpus", size="sm")
            with gr.Tab("Configuración"):
                gr.Markdown("Configuración activa (solo lectura, sin secretos).")
                b_cfg = gr.Button("Actualizar", size="sm")
                config_md = gr.Markdown()

        def on_login(token, request: gr.Request):
            try:
                ad.guard(token, _ip(request))
            except PermissionError as e:
                return (gr.update(), gr.update(), "", f"**{esc(str(e))}**", gr.update(), gr.update(), gr.update(), gr.update())
            ip = _ip(request)
            return (gr.update(visible=False), gr.update(visible=True), token, "", ad.resumen(token, ip), ad.cargar(token, ip),
                    ad.memoria(token, ip), ad.configuracion(token, ip))

        salidas_login = [login_box, panel, token_state, msg, resumen_md, editor, memoria_md, config_md]
        entrar.click(on_login, [tok], salidas_login, api_name=False)
        tok.submit(on_login, [tok], salidas_login, api_name=False)
        def h_resumen(t, request: gr.Request):
            return seguro(ad.resumen, t, request=request)

        def h_cargar(t, request: gr.Request):
            return seguro(ad.cargar, t, request=request)

        def h_validar(x, t, request: gr.Request):
            return seguro(ad.validar, x, t, request=request)

        def h_guardar(x, t, request: gr.Request):
            return seguro(ad.guardar, x, t, request=request)

        def h_importar(f, t, request: gr.Request):
            return seguro(ad.importar, f, t, request=request)

        def h_borrador(t, request: gr.Request):
            return seguro(ad.borrador, t, request=request)

        def h_memoria(t, request: gr.Request):
            return seguro(ad.memoria, t, request=request)

        def h_reindexar(t, request: gr.Request):
            mensaje = seguro(ad.reindexar, t, request=request)
            return mensaje, seguro(ad.memoria, t, request=request)

        def h_cache(t, request: gr.Request):
            mensaje = seguro(ad.vaciar_cache, t, request=request)
            return mensaje, seguro(ad.memoria, t, request=request)

        def h_config(t, request: gr.Request):
            return seguro(ad.configuracion, t, request=request)

        refrescar.click(h_resumen, [token_state], [resumen_md], api_name=False)
        b_mem.click(h_memoria, [token_state], [memoria_md], api_name=False)
        b_reidx.click(h_reindexar, [token_state], [estado_mem, memoria_md], api_name=False)
        b_cache.click(h_cache, [token_state], [estado_mem, memoria_md], api_name=False)
        b_cfg.click(h_config, [token_state], [config_md], api_name=False)
        b_cargar.click(h_cargar, [token_state], [editor], api_name=False)
        b_validar.click(h_validar, [editor, token_state], [estado], api_name=False)
        b_guardar.click(h_guardar, [editor, token_state], [estado], api_name=False)
        b_imp.click(h_importar, [archivo, token_state], [prop1, res1], api_name=False)
        b_bor.click(h_borrador, [token_state], [prop2, res2], api_name=False)

        def agregar(actual, propuesta):
            return ((actual or "").rstrip() + "\n\n" + propuesta.strip() + "\n") if (propuesta or "").strip() else actual

        add1.click(agregar, [editor, prop1], [editor], api_name=False)
        add2.click(agregar, [editor, prop2], [editor], api_name=False)
    return demo
