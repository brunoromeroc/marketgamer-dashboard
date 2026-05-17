import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from velocidad_restock import merge_snapshot, recortar_historial


def test_merge_snapshot_agrega_dia():
    h = {"2026-05-16": {"A": 3}}
    out = merge_snapshot(h, "2026-05-17", {"A": 0, "B": 5})
    assert out["2026-05-16"] == {"A": 3}
    assert out["2026-05-17"] == {"A": 0, "B": 5}


def test_merge_snapshot_idempotente_pisa_mismo_dia():
    h = {"2026-05-17": {"A": 9}}
    out = merge_snapshot(h, "2026-05-17", {"A": 1})
    assert out == {"2026-05-17": {"A": 1}}
    assert len(out) == 1


def test_merge_snapshot_no_muta_original():
    h = {"2026-05-16": {"A": 3}}
    merge_snapshot(h, "2026-05-17", {"A": 0})
    assert h == {"2026-05-16": {"A": 3}}


def test_recortar_historial_mantiene_ultimas_n_fechas():
    h = {f"2026-01-{d:02d}": {"A": d} for d in range(1, 11)}  # 10 fechas
    out = recortar_historial(h, max_dias=3)
    assert sorted(out.keys()) == ["2026-01-08", "2026-01-09", "2026-01-10"]


def test_recortar_historial_sin_recorte_si_pocas():
    h = {"2026-01-01": {"A": 1}, "2026-01-02": {"A": 2}}
    out = recortar_historial(h, max_dias=180)
    assert out == h


from velocidad_restock import explotar_items


def test_explotar_items_separa_lineas():
    df = pd.DataFrame([
        {"Fecha": "2026-05-01", "Items": [
            {"producto": "A", "cantidad": 2, "costo": 100.0},
            {"producto": "B", "cantidad": 1, "costo": 50.0},
        ]},
        {"Fecha": "2026-05-02", "Items": [
            {"producto": "A", "cantidad": 3, "costo": 100.0},
        ]},
    ])
    out = explotar_items(df)
    a = out[out["Producto"] == "A"]
    assert list(a["Cantidad"]) == [2, 3]
    assert set(out["Producto"]) == {"A", "B"}
    assert list(out.columns) == ["Fecha", "Producto", "Cantidad", "Costo"]


def test_explotar_items_ignora_filas_sin_items():
    df = pd.DataFrame([
        {"Fecha": "2026-05-01", "Items": []},
        {"Fecha": "2026-05-02", "Items": None},
        {"Fecha": "2026-05-03", "Items": [{"producto": "A", "cantidad": 1, "costo": 9.0}]},
    ])
    out = explotar_items(df)
    assert len(out) == 1
    assert out.iloc[0]["Producto"] == "A"


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests OK")


if __name__ == "__main__":
    _run()
