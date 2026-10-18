"""API FastAPI: chat público de solo consulta + endpoints de administración con token."""
from __future__ import annotations

import hmac
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import gradio as gr
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .admin import ADMIN_CSS, build_admin_ui
from .config import settings
from .service import Service
from .ui import CSS, JS, THEME, build_ui

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("asistente_te")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "service"):
        app.state.service = Service(settings)
    yield


app = FastAPI(title=f"{settings.app_name} · TE Connectivity Hermosillo", version="3.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_fails: dict[str, deque] = defaultdict(deque)


def get_service() -> Service:
    if not hasattr(app.state, "service"):
        app.state.service = Service(settings)
    return app.state.service


def svc(request: Request) -> Service:
    return get_service()


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    return (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "?"))[:64]


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    return resp


class ConsultaIn(BaseModel):
    texto: str = Field(min_length=1, max_length=settings.max_query_chars)
    perfil: Literal["operador", "administrativo", "todos"] = "todos"


class FeedbackIn(BaseModel):
    util: bool


@app.get("/health")
def health(request: Request):
    return {"status": "ok", "entradas": len(svc(request).index.entries)}


@app.post("/api/consulta")
def consulta(body: ConsultaIn, request: Request, x_client_id: str | None = Header(default=None)):
    s = svc(request)
    ip, cid = client_ip(request), (x_client_id or "")[:64]
    if not s.quota.rate_ok(ip, cid):
        raise HTTPException(429, "Demasiadas consultas seguidas. Espera un minuto e inténtalo de nuevo.")
    t0 = time.time()
    try:
        out = s.responder(body.texto, body.perfil, ip, cid)
    except Exception:  # nunca 500 al usuario
        log.exception("error inesperado en consulta")
        return JSONResponse({"tipo": "error", "respuesta": "Ocurrió un error. Inténtalo de nuevo en un momento.",
                             "fichas": [], "fuentes": [], "verificacion": "no_aplica", "advertencias": [],
                             "uso": {}})
    log.info("consulta tipo=%s ms=%d tokens=%s", out["tipo"], (time.time() - t0) * 1000,
             out["uso"].get("tokens_consulta"))
    return out


@app.post("/api/feedback")
def feedback(body: FeedbackIn, request: Request):
    svc(request).metrics["util_si" if body.util else "util_no"] += 1
    return {"ok": True}


# ---------------- administración ----------------
def admin(request: Request, authorization: str | None, x_admin_token: str | None) -> None:
    ip, now = client_ip(request), time.time()
    q = _fails[ip]
    while q and now - q[0] > 600:
        q.popleft()
    if len(q) >= 5:
        raise HTTPException(429, "Demasiados intentos.")
    if not settings.admin_token:
        raise HTTPException(403, "Administración deshabilitada (falta ADMIN_TOKEN).")
    token = x_admin_token or (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), settings.admin_token.encode()):
        q.append(now)
        raise HTTPException(401, "Token inválido.")


@app.post("/api/admin/reindex")
def admin_reindex(request: Request, authorization: str | None = Header(default=None),
                  x_admin_token: str | None = Header(default=None)):
    admin(request, authorization, x_admin_token)
    return svc(request).reindex()


@app.get("/api/admin/estado")
def admin_estado(request: Request, authorization: str | None = Header(default=None),
                 x_admin_token: str | None = Header(default=None)):
    admin(request, authorization, x_admin_token)
    return svc(request).estado()


@app.get("/api/admin/reportes")
def admin_reportes(request: Request, authorization: str | None = Header(default=None),
                   x_admin_token: str | None = Header(default=None)):
    admin(request, authorization, x_admin_token)
    sv = svc(request)
    return {"reportes": sorted(sv.reportes.values(), key=lambda r: -r["veces"]),
            "temas_populares": sv.popularidad.most_common(10)}


# ---------------- interfaz Gradio (debe montarse DESPUÉS de definir las rutas de la API) ----------------
# El panel /admin se monta ANTES: la interfaz pública en "/" captura cualquier otra ruta.
@app.get("/admin", include_in_schema=False)
def admin_sin_barra():
    return RedirectResponse("/admin/")


app = gr.mount_gradio_app(app, build_admin_ui(get_service), path="/admin", theme=THEME, css=CSS + ADMIN_CSS, js=JS,
                          footer_links=[])
app = gr.mount_gradio_app(app, build_ui(get_service), path="/", theme=THEME, css=CSS, js=JS,
                          favicon_path=str(STATIC / "favicon.png"), footer_links=[])
