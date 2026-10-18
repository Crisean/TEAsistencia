import pytest

from app.service import Service


@pytest.fixture
def idx(cfg):
    return Service(cfg).index


@pytest.mark.parametrize("q,esperado", [
    ("¿Dónde entrego mi incapacidad del IMSS?", "recursos-humanos"),
    ("necesito una constancia laboral", "recursos-humanos"),
    ("aclaracion de pago", "nomina"),
    ("contraseña del wifi", "sistemas-ti"),
    ("instruccion de trabajo vigente", "control-documentos"),
    ("verificar pulsera esd", "control-esd"),
    ("donde estan los baños", "mapa-areas"),
    ("direccion de la planta", "te-planta-hermosillo"),
])
def test_top1(idx, q, esperado):
    assert idx.search(q, "todos")[0].entry.id == esperado


def test_perfil_prioriza_audiencia(idx):
    assert idx.search("requisicion", "operador")[0].entry.id == "almacen"
    assert idx.search("requisicion", "administrativo")[0].entry.id == "compras-requisiciones"


def test_sin_terminos_no_devuelve_nada(idx):
    assert idx.search("que de la el", "todos") == []


def test_fuera_de_alcance_baja_relevancia(cfg):
    s = Service(cfg)
    hits = s.index.search("cuanto cuesta un boleto de avion a Paris", "todos")
    assert not s._relevant(hits)
