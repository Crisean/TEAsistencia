# Asistente TE · TE Connectivity Hermosillo

Asistente interno de preguntas y respuestas para el personal de la planta **TE Connectivity Data & Devices** en Hermosillo, Sonora. Sirve para:

- **Acceder rápido a documentación**: procedimientos, instrucciones de trabajo, formatos y políticas.
- **Respuestas rápidas**: horarios, extensiones, responsables y requisitos de cada área.
- **Localizar áreas** de la planta: dónde está Calidad, Enfermería, RH, el almacén, etc.

La información vive en un catálogo de texto plano (`data/corpus.txt`) que mantiene el equipo administrativo; la IA solo se usa como último recurso, con un consumo de tokens mínimo y acotado por usuario.

**Planta:** Latitud Oriente Sur 74, Colonia Parque Industrial, C.P. 83175, Hermosillo, Sonora · [Google Maps](https://maps.app.goo.gl/GTqTkmdj6zFkrEfU6)

![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Gradio](https://img.shields.io/badge/Gradio-6.30-F97316)
![Deploy](https://img.shields.io/badge/deploy-Render-46E3B7)

> **Antes de publicar:** las fichas marcadas con «(ejemplo)» en `data/corpus.txt` son plantillas. Sustituye responsables, extensiones, ubicaciones internas y horarios por los datos oficiales de la planta, y no registres información confidencial de clientes, productos ni datos personales.

## Contenido

- [Características](#características)
- [Arquitectura](#arquitectura)
- [Identidad visual](#identidad-visual)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Inicio rápido](#inicio-rápido)
- [Configuración](#configuración)
- [Catálogo (corpus)](#catálogo-corpus)
- [Administración](#administración)
- [API HTTP](#api-http)
- [Pruebas y calidad](#pruebas-y-calidad)
- [Subir a GitHub](#subir-a-github)
- [Despliegue en Render](#despliegue-en-render)
- [Seguridad y privacidad](#seguridad-y-privacidad)
- [Limitaciones conocidas](#limitaciones-conocidas)

## Características

- **Catálogo como fuente de verdad.** Toda la información vive en `data/corpus.txt`. Agregar un área o documento es agregar una ficha, no cambiar código.
- **Ubicación de áreas.** Cada ficha tiene `UBICACION` con puntos de referencia, y la ficha `mapa-areas` describe la distribución general de la planta.
- **Respuesta al punto.** «¿Dónde está Calidad?» devuelve solo la ubicación; «¿y la extensión?» reutiliza el último tema.
- **Coste de tokens mínimo.** La mayoría de las consultas se resuelven con búsqueda local y no gastan tokens.
- **Sin datos inventados.** Horarios, extensiones, correos y ubicaciones se toman siempre de la ficha, nunca los redacta el modelo.
- **Perfiles** `operador`, `administrativo` y `todos` para priorizar la información de cada tipo de personal.
- **Límites de uso** por consulta, por usuario y por día, y un tope global.
- **Mejora continua.** El personal puede informar cuando falta información; el administrador convierte esos informes en nuevas fichas.
- **Panel de administración** con editor del catálogo, importación de documentos (PDF, HTML, TXT, MD) asistida por IA y publicación en GitHub.

## Arquitectura

```
                      ┌──────────────────────────── FastAPI ────────────────────────────┐
 Navegador ──► Gradio │  /           chat del personal (interfaz Gradio)                 │
                      │  /admin      panel de administración (token)                     │
                      │  /api/*      API HTTP · /health · /docs                          │
                      └───────┬──────────────────────────────────────────────────────────┘
                              ▼
                       app/service.py  (pipeline de consulta)
                              │
   ┌──────────┬───────────────┼────────────────┬───────────────┐
   ▼          ▼               ▼                ▼               ▼
 safety    intent       índice BM25        quota / caché     llm.py
(derivar) (qué dato    (tags, sinónimos,  (cupos, límites)  (Anthropic u
           se pide)     prefijos)                            OpenAI-compatible)
                              ▲
                  data/corpus.txt ──► app.build_corpus ──► data/index.json
```

| Nivel | Comportamiento | Tokens |
|---|---|---|
| 0 | Derivación de emergencias y temas de salud, legales o psicológicos; caché; aclaración cuando se pregunta un dato sin indicar el área | 0 |
| 1 | Respuesta al punto (ubicación, horario, extensión…), seguimiento y ficha directa para consultas claras | 0 |
| 1b | Reformulación con palabras clave si la búsqueda local no encuentra nada (una vez por pregunta, con caché) | ≈ 100 |
| 2 | Una llamada al modelo con un máximo de 3 fichas recortadas, en streaming | ≈ 860 máx. |

## Identidad visual

Modo oscuro con la paleta del proyecto y el naranja de la marca TE como acento:

| Color | Uso |
|---|---|
| `#08090B` | Fondo |
| `#EEEFF0` | Texto principal |
| `#2E4956` / `#39505F` | Burbujas del usuario, barras de desplazamiento y degradado del encabezado |
| `#65899F` | Base de enlaces (tinte claro `#9DBBCD` para contraste AA) |
| `#EB8002` | Naranja TE (tomado del logotipo): acentos, botón de envío |

El logotipo está en `app/static/logo.png` (original), `logo_dark.png` (encabezado) y `favicon.png`. Los colores se definen al inicio de `app/ui.py`.

## Estructura del repositorio

```
app/
  main.py          FastAPI: API, cabeceras de seguridad y montaje de Gradio
  ui.py            interfaz del chat (tema TE, streaming)
  admin.py         panel /admin y publicación del catálogo en GitHub
  admin_ai.py      importación de documentos y borradores con IA
  service.py       pipeline de consulta
  index.py         índice BM25, sinónimos y cobertura
  intent.py        detección local del dato solicitado
  corpus.py        parser y validación de corpus.txt
  llm.py           cliente HTTP del modelo
  quota.py         ritmo, cupos diarios y tope global
  safety.py        filtro de derivación
  build_corpus.py  CLI: validar e indexar
  importar.py      CLI: proponer fichas desde un documento
  static/          logotipo y favicon de TE
data/
  corpus.txt       catálogo de áreas, documentación y servicios
  sinonimos.txt    vocabulario coloquial de planta
  info_planta.md   dirección y enlace a Google Maps (panel «i» del chat)
  plantilla_entrada.txt  plantilla para nuevas fichas
  index.json       índice precalculado
tests/             pytest
.github/workflows/ci.yml  integración continua
render.yaml        Blueprint de Render
```

## Inicio rápido

Requisitos: Python 3.12.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                  # edita LLM_API_KEY, ADMIN_TOKEN, ID_SALT
python -m app.build_corpus            # valida el catálogo y genera data/index.json
set -a; source .env; set +a           # exporta las variables del entorno
uvicorn app.main:app --reload         # http://localhost:8000
```

Con `LLM_PROVIDER=none` la aplicación funciona completa sin invocar al modelo (respuestas directas y al punto, sin reformulación ni redacción).

## Configuración

Todo se controla con variables de entorno (ver `.env.example`). Las claves y tokens nunca deben subirse al repositorio.

| Variable | Descripción | Por defecto |
|---|---|---|
| `APP_NAME` | Nombre visible del asistente | `Asistente TE` |
| `LLM_PROVIDER` | `anthropic`, `openai` (compatible) o `none` | `anthropic` |
| `MODEL_NAME` | Modelo a utilizar; verifica el identificador vigente con tu proveedor | `claude-haiku-5-5` |
| `LLM_API_KEY` | Clave del proveedor (secreta) | — |
| `LLM_BASE_URL` | URL base alternativa para proveedores compatibles | — |
| `ADMIN_TOKEN` | Token del panel y de `/api/admin/*` (secreto) | — |
| `ID_SALT` | Sal para el hash de identificadores anónimos (secreta) | `cambia-esto` |
| `TIMEZONE` | Zona horaria de la planta (cupos diarios y fechas) | `America/Hermosillo` |
| `MAX_QUERY_CHARS` | Longitud máxima de la pregunta | `300` |
| `TOP_K` | Fichas máximas enviadas al modelo | `3` |
| `MAX_CONTEXT_CHARS` | Presupuesto de contexto por consulta | `1800` |
| `MAX_OUTPUT_TOKENS` | Tokens máximos de salida | `250` |
| `USER_TOKENS_DAY` / `USER_QUERIES_DAY` | Cupo diario por usuario | `10000` / `15` |
| `REQ_PER_MIN` | Consultas por minuto por usuario | `8` |
| `IP_MULTIPLIER` | Holgura del cupo por IP (redes compartidas) | `5` |
| `GLOBAL_TOKENS_DAY` | Tope diario de todo el servicio | `300000` |
| `MIN_SCORE` / `MIN_COVERAGE` | Umbrales de relevancia | `1.2` / `0.34` |
| `DIRECT_ENABLED` | Permite responder con la ficha sin invocar al modelo | `true` |
| `STALE_DAYS` | Antigüedad a partir de la cual se avisa de vigencia | `365` |
| `CACHE_SIZE` / `CACHE_TTL_S` | Caché de respuestas | `500` / `86400` |
| `REPORTS_PER_DAY` | Informes de «sin respuesta» por usuario y día | `5` |
| `REPORT_WEBHOOK_URL` | Webhook opcional que recibe los informes | — |
| `IMPORT_MAX_CHUNKS` / `IMPORT_CHUNK_CHARS` | Límites de la importación asistida | `6` / `6000` |
| `GITHUB_TOKEN`, `GITHUB_REPO` | Publicación del catálogo desde el panel | — |
| `GITHUB_BRANCH`, `GITHUB_CORPUS_PATH` | Rama y ruta del catálogo | `main`, `data/corpus.txt` |
| `SHOW_ADMIN_LINK` | Muestra un enlace discreto «Administración» al pie del chat; `false` lo oculta (el panel sigue en `/admin`) | `true` |

> Los cupos viven en memoria y se reinician con el servicio. Configura además un tope de gasto en el panel del proveedor del modelo.

## Catálogo (corpus)

`data/corpus.txt` contiene una ficha por área, procedimiento o servicio de la planta. El formato es de texto plano, pensado para editarse a mano:

```
### control-documentos
TITULO: Control de Documentos (procedimientos e instrucciones de trabajo)
PUESTO: Control de Documentos · Sistema de Calidad
CATEGORIA: documentacion
AUDIENCIA: todos
TAGS: procedimiento, instruccion de trabajo, formato, sop, version vigente, documento controlado
RESPONSABLE: Nombre o puesto
CORREO: documentos.hermosillo@ejemplo.com
TELEFONO: Ext. 1210
UBICACION: Edificio administrativo, nivel 2, área de Calidad
HORARIO: Lunes a viernes, 8:00 a 17:00
WEB: enlace a la intranet
ACTUALIZADO: 2026-10-17
PREGUNTA: ¿Dónde consulto un procedimiento o instrucción de trabajo?
--
Texto libre con frases cortas y literales: qué es, dónde está, pasos y qué puede variar.
```

| Campo | Uso |
|---|---|
| `### id` | Identificador único (minúsculas y guiones) |
| `TITULO` | Obligatorio |
| `TAGS` | Palabras que los usuarios escribirían, con sinónimos coloquiales. Principal factor de recuperación |
| `PUESTO`, `RESPONSABLE`, `CORREO`, `TELEFONO`, `UBICACION`, `HORARIO`, `WEB` | Ficha de contacto y respuestas al punto |
| `ACTUALIZADO` | `AAAA-MM-DD`; habilita el aviso de vigencia |
| `PREGUNTA` | Pregunta modelo mostrada como ejemplo en el chat; los temas más consultados aparecen primero |
| `CATEGORIA`, `AUDIENCIA` | Clasificación. `AUDIENCIA`: `operador`, `administrativo` o `todos` |

Recomendaciones: un tema por ficha, menos de 1,200 caracteres de texto, ubicaciones con puntos de referencia y sin datos personales. Una ficha que contenga `[COMPLETAR]` no pasa la validación.

`data/sinonimos.txt` define un grupo por línea (`gafete, credencial, identificacion`). Se aplica a la consulta, no al documento.

## Administración

### Panel web

`/admin` (requiere `ADMIN_TOKEN`):

- **Resumen:** temas más consultados, informes de «sin respuesta», fichas desactualizadas y avisos de validación.
- **Corpus:** editor con validación y **Guardar y publicar**. El cambio se aplica de inmediato; con `GITHUB_TOKEN` y `GITHUB_REPO` se registra además un commit y Render redespliega.
- **Memoria:** estado de lo cargado frente al archivo del catálogo (indica si el índice quedó desactualizado), caché e informes pendientes. Botones **Reindexar ahora** (recarga `corpus.txt` y reconstruye el índice) y **Vaciar caché** (respuestas y reformulaciones; no reinicia los cupos de los usuarios).
- **Importar con IA:** carga de PDF, HTML, TXT o MD (máx. 3 MB). Propone fichas para revisión; los correos, teléfonos y URLs ausentes del documento original se eliminan de la propuesta.
- **Borrador desde informes:** genera fichas con `[COMPLETAR]` a partir de las preguntas sin respuesta más frecuentes. No pueden publicarse hasta completarse con información oficial.
- **Configuración:** valores activos de solo lectura con recomendaciones (clave de IA ausente, `ID_SALT` por defecto, token corto, GitHub sin configurar). Los secretos nunca se muestran: solo si están configurados. Para cambiarlos se editan las variables de entorno y se redespliega.

El token de GitHub debe ser *fine-grained*, limitado a este repositorio y con permiso *Contents: Read and write*.

### Línea de comandos

```bash
python -m app.build_corpus                  # valida e indexa (0 tokens)
python -m app.build_corpus --check          # solo valida (CI)
python -m app.build_corpus --sugerir-tags   # sugiere tags para fichas sin TAGS
python -m app.importar doc.pdf --dry-run    # fragmentos y coste estimado, sin llamar al modelo
python -m app.importar doc.pdf              # escribe data/propuestas.txt
```

## API HTTP

Documentación interactiva en `/docs`.

| Método y ruta | Descripción | Acceso |
|---|---|---|
| `GET /health` | Estado del servicio | Público |
| `POST /api/consulta` | `{"texto": str, "perfil": "operador\|administrativo\|todos"}` → respuesta con fichas y uso. Cabecera opcional `X-Client-Id` | Público, con límite de ritmo |
| `POST /api/feedback` | `{"util": bool}` | Público |
| `GET /api/admin/estado` | Estado del índice, métricas y cuotas | Token |
| `GET /api/admin/reportes` | Informes de «sin respuesta» y temas populares | Token |
| `POST /api/admin/reindex` | Recarga el catálogo | Token |

El token se envía en `X-Admin-Token` o `Authorization: Bearer <token>`.

## Pruebas y calidad

```bash
ruff check .
python -m app.build_corpus --check
pytest -q --cov=app
```

Las pruebas no realizan llamadas de red y usan el catálogo real de `data/corpus.txt`; si cambias fichas de ejemplo, ajusta las pruebas que las mencionan: el modelo, GitHub y el streaming se simulan. Cubren el parser del corpus, la recuperación, los cupos, el pipeline (abstención, derivación, caché, seguimiento, reformulación, streaming y degradación), la importación con verificación de contactos, el panel y la API. El flujo de integración continua (`.github/workflows/ci.yml`) ejecuta lint, validación del catálogo, pruebas con cobertura y `pip-audit`.

## Subir a GitHub

1. Crea un repositorio nuevo en GitHub (recomendado: **privado**, p. ej. `te-asistente`).
2. Desde la carpeta del proyecto:

```bash
git init
git add .
git commit -m "Asistente TE: versión inicial"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/te-asistente.git
git push -u origin main
```

   O, sin terminal: en GitHub usa **Add file › Upload files**, arrastra el contenido de la carpeta (incluida `.github/`) y confirma.
3. La pestaña **Actions** ejecuta el flujo de CI (lint, validación del catálogo y pruebas) en cada push.

`.env` está en `.gitignore`: las claves nunca deben subirse.

## Despliegue en Render

**Opción A — Blueprint (recomendada):** en Render elige **New › Blueprint**, conecta el repositorio y Render leerá `render.yaml`. Genera `ADMIN_TOKEN` e `ID_SALT` automáticamente; solo te pedirá `LLM_API_KEY` (y opcionalmente `GITHUB_TOKEN` / `GITHUB_REPO`).

**Opción B — Web Service manual:**

1. **New › Web Service** y conecta el repositorio.
2. Configura:
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt && python -m app.build_corpus --check`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
3. Variables de entorno: `PYTHON_VERSION=3.12.8`, `LLM_API_KEY`, `ADMIN_TOKEN`, `ID_SALT`, `TIMEZONE=America/Hermosillo`; opcionalmente `GITHUB_TOKEN`, `GITHUB_REPO` y `REPORT_WEBHOOK_URL`.

Cada push a `main` redespliega automáticamente. El chat queda en `https://TU-APP.onrender.com/` y el panel en `/admin` (entra con el valor de `ADMIN_TOKEN`, visible en Render › Environment).

Verifica los límites vigentes del plan elegido: en el plan gratuito el servicio se suspende por inactividad (la primera consulta tarda en despertar), tiene memoria limitada y no ofrece disco persistente, por lo que los cambios hechos desde el panel sin `GITHUB_TOKEN` y los informes en memoria se pierden al reiniciar. Para uso diario en planta conviene un plan de pago.

> **Información interna:** la URL de Render es pública. Si el catálogo llega a contener información que no deba ser pública, protege el acceso (p. ej. plan con IP permitidas, SSO corporativo o un proxy autenticado) y consulta a TI y a Seguridad de la Información de la planta antes de publicarlo.

## Seguridad y privacidad

- Sin cuentas, sin base de datos y sin historial: la conversación no se guarda.
- Los cupos usan un identificador anónimo del navegador y la IP, ambos con hash salado y solo en memoria.
- La pregunta solo se almacena si el usuario pulsa «Informar que falta esta información»; se trunca y se enmascaran correos y teléfonos.
- El panel de administración nunca muestra secretos; el enlace del chat es discreto y desactivable, pero la protección real es el token.
- Los endpoints de administración usan comparación de token en tiempo constante, bloqueo tras 5 intentos fallidos en 10 minutos y se revalidan en cada acción del panel.
- Todo el contenido del catálogo y de los usuarios se muestra escapado; la API incluye `Content-Security-Policy` y `X-Content-Type-Options`.
- Las fichas se tratan como datos delimitados; correos y extensiones no se envían al modelo.
- Las dependencias están fijadas y se auditan en CI.

## Limitaciones conocidas

- La búsqueda es léxica: la calidad depende de buenos `TAGS` y sinónimos. Los umbrales de relevancia deben calibrarse con el catálogo real.
- Los contadores de cupo, los informes y la popularidad de temas viven en memoria y se reinician con el servicio.
- Las respuestas directas devuelven datos de la ficha, por lo que su exactitud depende de que el catálogo esté al día (`ACTUALIZADO`).
- Los selectores de estilo dependen de los nombres internos de Gradio 6.30; actualizar la versión puede requerir ajustar el CSS en `app/ui.py`.
