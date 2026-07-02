import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from operacion import edad_legible, parse_senales


def test_edad_legible():
    assert edad_legible(None) == "sin datos"
    ahora = 10_000_000_000
    assert edad_legible(ahora - 5 * 60_000, ahora) == "hace 5 min"
    assert edad_legible(ahora - 3 * 3_600_000, ahora) == "hace 3 h"
    assert edad_legible(ahora - 72 * 3_600_000, ahora) == "hace 3 dias"


def test_parse_senales_completo():
    data = {
        "snapshot": {
            "fichas": {"total": 68, "rojas": 1},
            "clientes": {"vip": 54},
            "automatizaciones": {"pendientes_tracking": 4, "envio_habilitado": True},
        },
        "snapshot_ts": 123,
        "merki_7d": {"total_messages": 10, "consultas_recientes": [{"ts": 1, "texto": "hola"}]},
    }
    op = parse_senales(data)
    assert op["fichas"]["total"] == 68 and op["fichas"]["amarillas"] == 0
    assert op["clientes"]["vip"] == 54
    assert op["automatizaciones"]["pendientes_tracking"] == 4
    assert op["envio_habilitado"] is True
    assert op["merki"]["total_messages"] == 10
    assert op["merki"]["consultas"][0]["texto"] == "hola"


def test_parse_senales_vacio_no_levanta():
    op = parse_senales(None)
    assert op["snapshot_ts"] is None
    assert op["fichas"]["total"] == 0
    assert op["merki"]["consultas"] == []
