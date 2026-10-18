import pytest

from app.intent import analizar


@pytest.mark.parametrize("q,attrs,entidad", [
    ("¿A qué hora abre la biblioteca?", ["horario"], ["biblioteca"]),
    ("¿y el teléfono?", ["telefono"], []),
    ("horario y teléfono de nómina", ["horario", "telefono"], ["nomina"]),
    ("necesito el contacto", ["telefono", "correo", "web"], []),
    ("¿Quién es el responsable de servicio social?", ["responsable"], ["servicio", "social"]),
    ("¿Cómo solicito mis vacaciones?", [], ["solicito", "vacacion"]),
    ("No puedo conectarme al Wi-Fi", [], ["conectarme", "wi", "fi"]),
])
def test_analizar(q, attrs, entidad):
    a, e = analizar(q)
    assert a == attrs and e == entidad


def test_donde_cuenta_como_ubicacion_aunque_sea_palabra_vacia():
    a, e = analizar("¿Dónde entrego mi incapacidad?")
    assert a == ["ubicacion"] and "incapacidad" in e and "donde" not in e
