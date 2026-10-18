"""Filtro de entrada determinista (0 tokens): emergencias y temas que requieren un profesional."""
import re

from .textutil import strip_accents

_PATTERNS = {
    "emergencia": r"emergenc|urgenc|ambulancia|incendio|sismo|temblor|balacera|disparos|"
                  r"suicid|me quiero (morir|matar)|quiero morir|autolesi|me estoy desangrando|infarto|desmay|"
                  r"me estan (golpeando|atacando|amenazando)",
    "salud": r"medicament|dosis|sintoma|diagnostic|enfermedad|dolor de|receta medica|embaraz|infeccion|"
             r"que me tomo|que puedo tomar",
    "legal": r"abogado|demandar|demanda legal|juicio|amparo|denuncia penal",
    "psico": r"ansiedad|depresion|ataque de panico|crisis nerviosa|me siento muy mal|terapia",
}
_COMPILED = {k: re.compile(v) for k, v in _PATTERNS.items()}

MENSAJES = {
    "salud": "No puedo dar orientación médica. Para temas de salud acude a la Enfermería / Servicio Médico de la planta "
             "o a tu clínica del IMSS.",
    "legal": "No puedo dar asesoría legal. Consulta a Recursos Humanos, al área legal de la empresa o a un profesional.",
    "psico": "No puedo dar orientación psicológica. Hay personas que pueden acompañarte; "
             "acude a Recursos Humanos o a Enfermería para que te canalicen, o busca a un profesional.",
}


def classify(texto: str) -> str | None:
    t = strip_accents(texto.lower())
    for tipo in ("emergencia", "salud", "psico", "legal"):
        if _COMPILED[tipo].search(t):
            return tipo
    return None
