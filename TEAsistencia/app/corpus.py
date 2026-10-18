"""Lectura y validación de data/corpus.txt (formato de bloques, editable a mano)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from .config import hoy

AUDIENCIAS = {"operador", "administrativo", "todos"}
CAMPOS = {"TITULO", "PUESTO", "AUDIENCIA", "TAGS", "RESPONSABLE", "CORREO", "TELEFONO",
          "UBICACION", "HORARIO", "WEB", "ACTUALIZADO", "CATEGORIA", "PREGUNTA"}
_ID = re.compile(r"^[a-z0-9][a-z0-9\-]{1,60}$")
_KV = re.compile(r"^([A-ZÁÉÍÓÚÑ_]+)\s*:\s*(.*)$")
_MAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class Entry:
    id: str
    titulo: str
    puesto: str = ""
    audiencia: list[str] = field(default_factory=lambda: ["todos"])
    categoria: str = ""
    tags: list[str] = field(default_factory=list)
    responsable: str = ""
    correo: str = ""
    telefono: str = ""
    ubicacion: str = ""
    horario: str = ""
    web: str = ""
    actualizado: str = ""  # ISO yyyy-mm-dd o ""
    pregunta: str = ""  # pregunta modelo que se muestra como ejemplo en el chat
    texto: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def age_days(self, today: date | None = None) -> int | None:
        try:
            d = datetime.strptime(self.actualizado, "%Y-%m-%d").date()  # noqa: DTZ007 (solo fecha)
        except ValueError:
            return None
        return ((today or hoy()) - d).days


@dataclass
class Problem:
    level: str  # "error" | "aviso"
    entry_id: str
    msg: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.entry_id}: {self.msg}"


def _slug(s: str) -> str:
    return s.strip().lower().replace(" ", "-")


def _split_blocks(text: str) -> list[tuple[str, list[str]]]:
    blocks, cur_id, cur = [], None, []
    for line in text.splitlines():
        if line.startswith("### "):
            if cur_id is not None:
                blocks.append((cur_id, cur))
            cur_id, cur = _slug(line[4:]), []
        elif cur_id is not None:
            cur.append(line)
    if cur_id is not None:
        blocks.append((cur_id, cur))
    return blocks


def parse_corpus(text: str, permitir_pendientes: bool = False) -> tuple[list[Entry], list[Problem]]:
    entries: list[Entry] = []
    problems: list[Problem] = []
    seen: set[str] = set()
    for eid, lines in _split_blocks(text):
        start = len(problems)
        if not _ID.match(eid):
            problems.append(Problem("error", eid, "ID inválido (usa minúsculas, números y guiones)."))
        if eid in seen:
            problems.append(Problem("error", eid, "ID repetido."))
        seen.add(eid)

        header: dict[str, str] = {}
        body_lines: list[str] = []
        in_body = False
        for line in lines:
            if in_body:
                body_lines.append(line)
            elif line.strip() == "--":
                in_body = True
            elif not line.strip() or line.lstrip().startswith("//"):
                continue
            else:
                m = _KV.match(line)
                if not m:
                    problems.append(Problem("aviso", eid, f"Línea de encabezado ignorada: {line[:40]!r}"))
                    continue
                k, v = m.group(1), m.group(2).strip()
                if k not in CAMPOS:
                    problems.append(Problem("aviso", eid, f"Campo desconocido ignorado: {k}"))
                    continue
                header[k] = v
        if not in_body:
            problems.append(Problem("aviso", eid, "Falta la línea '--' que separa encabezado y texto."))

        titulo = header.get("TITULO", "")
        if not titulo:
            problems.append(Problem("error", eid, "Falta TITULO."))
        tags = [t.strip().lower() for t in header.get("TAGS", "").split(",") if t.strip()]
        if not tags:
            problems.append(Problem("aviso", eid, "Sin TAGS: se recuperará peor. Usa --sugerir-tags."))
        aud = [a.strip().lower() for a in header.get("AUDIENCIA", "todos").split(",") if a.strip()] or ["todos"]
        bad = [a for a in aud if a not in AUDIENCIAS]
        if bad:
            problems.append(Problem("aviso", eid, f"AUDIENCIA no válida {bad}; se usa 'todos'."))
            aud = ["todos"]
        act = header.get("ACTUALIZADO", "")
        if act:
            try:
                datetime.strptime(act, "%Y-%m-%d")  # noqa: DTZ007 (solo valida el formato)
            except ValueError:
                problems.append(Problem("aviso", eid, f"ACTUALIZADO debe ser AAAA-MM-DD (recibido {act!r})."))
                act = ""
        else:
            problems.append(Problem("aviso", eid, "Sin ACTUALIZADO: no se podrá avisar de vigencia."))
        mail = header.get("CORREO", "")
        if mail and not _MAIL.match(mail):
            problems.append(Problem("aviso", eid, f"CORREO con formato dudoso: {mail}"))
        texto = "\n".join(body_lines).strip()
        if not texto:
            problems.append(Problem("aviso", eid, "Texto vacío."))
        if not permitir_pendientes and "[COMPLETAR" in (texto + " ".join(header.values())):
            problems.append(Problem("error", eid, "Contiene [COMPLETAR]: termina la ficha con información oficial antes de publicar."))

        if any(p.level == "error" for p in problems[start:]):
            continue
        entries.append(Entry(
            id=eid, titulo=titulo, puesto=header.get("PUESTO", ""), audiencia=aud,
            categoria=header.get("CATEGORIA", ""), tags=tags,
            responsable=header.get("RESPONSABLE", ""), correo=mail,
            telefono=header.get("TELEFONO", ""), ubicacion=header.get("UBICACION", ""),
            horario=header.get("HORARIO", ""), web=header.get("WEB", ""),
            actualizado=act, pregunta=header.get("PREGUNTA", "")[:90], texto=texto))
    if not entries and not any(p.level == "error" for p in problems):
        problems.append(Problem("error", "-", "El corpus no contiene entradas ('### id')."))
    return entries, problems


def parse_synonyms(text: str) -> list[list[str]]:
    groups = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        g = [w.strip() for w in line.split(",") if w.strip()]
        if len(g) >= 2:
            groups.append(g)
    return groups
