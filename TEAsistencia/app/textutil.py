"""Normalización de texto en español: sin acentos, minúsculas, sin palabras vacías, stemming ligero."""
import re
import unicodedata

STOP = {"a", "al", "algo", "ante", "con", "contra", "cual", "cuales", "cuando", "cuanto", "cuanta", "de", "del", "desde", "donde", "dime", "e", "el", "ella", "ellos", "en", "entre", "era", "es", "esta", "estan", "este", "esto", "estos", "favor", "fue", "ha", "hay", "hola", "la", "las", "le", "les", "lo", "los", "me", "mi", "mis", "mas", "muy", "necesito", "ni", "no", "nos", "o", "os", "para", "pero", "por", "porque", "puedo", "puede", "pueden", "que", "quien", "quienes", "quiero", "se", "ser", "si", "sin", "sobre", "su", "sus", "saber", "sabes", "tambien", "tengo", "te", "tiene", "tienen", "todo", "tu", "tus", "un", "una", "uno", "unos", "unas", "y", "ya", "yo", "hacer", "hago", "como", "gustaria", "ayuda", "ayudame", "pido", "pedir", "llevar", "llevo", "necesita", "necesitas", "necesitar", "ocupo"}

_WORD = re.compile(r"[a-z0-9]+")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def stem(w: str) -> str:
    """Stemming mínimo para plurales (procedimientos->procedimiento, areas->area)."""
    if len(w) <= 3:
        return w
    if w.endswith(("ciones", "siones")):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokens(s: str, keep_stop: bool = False) -> list[str]:
    s = strip_accents(s.lower())
    out = []
    for w in _WORD.findall(s):
        if not keep_stop and w in STOP:
            continue
        out.append(stem(w))
    return out
