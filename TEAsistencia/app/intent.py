"""Detección local (0 tokens) de qué DATO pide el usuario: horario, teléfono, correo, ubicación, web o responsable.

Sirve para (a) responder al punto ("¿a qué hora abre la biblioteca?" -> solo el horario) y
(b) entender preguntas de seguimiento ("¿y el teléfono?") usando el último tema consultado.
"""
from __future__ import annotations

from .textutil import tokens

# clave -> (etiqueta visible, campo de la ficha, palabras que lo piden; ya sin acentos y en singular)
ATRIBUTOS: dict[str, tuple[str, str, set[str]]] = {
    "horario": ("Horario", "horario", {"horario", "hora", "abre", "abren", "cierra", "cierran", "atencion", "abierto"}),
    "telefono": ("Teléfono", "telefono", {"telefono", "llamar", "llamo", "celular", "whatsapp"}),
    "correo": ("Correo", "correo", {"correo", "email", "mail", "escribir", "escribo"}),
    "ubicacion": ("Ubicación", "ubicacion", {"ubicacion", "ubicado", "ubicada", "queda", "direccion", "domicilio", "piso", "donde"}),
    "web": ("Web", "web", {"web", "pagina", "sitio", "link", "enlace"}),
    "responsable": ("Responsable", "responsable", {"responsable", "encargado", "encargada", "coordinador", "coordinadora",
                                                   "director", "directora"}),
}
CONTACTO = ("telefono", "correo", "web")
_ALIAS_CONTACTO = {"contacto", "contactar", "comunicar", "comunico"}
_TODAS = set().union(*(w for _, _, w in ATRIBUTOS.values())) | _ALIAS_CONTACTO


def analizar(texto: str) -> tuple[list[str], list[str]]:
    """Devuelve (atributos pedidos, términos que nombran el tema). Si no hay tema, es pregunta de seguimiento o ambigua."""
    crudo = tokens(texto, keep_stop=True)  # "donde" es palabra vacía para buscar, pero indica ubicación
    attrs = [k for k, (_, _, palabras) in ATRIBUTOS.items() if any(t in palabras for t in crudo)]
    if any(t in _ALIAS_CONTACTO for t in crudo):
        attrs += [a for a in CONTACTO if a not in attrs]
    entidad = [t for t in tokens(texto) if t not in _TODAS]
    return attrs, entidad
