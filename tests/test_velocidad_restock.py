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


from velocidad_restock import dias_con_stock


def test_dias_con_stock_proxy_sin_stock_ahora():
    # Vendió 1/3 y 20/3, sin stock ahora, sin historial -> 1/3..20/3 = 20 días
    d = dias_con_stock(
        fechas_venta=["2026-03-01", "2026-03-20"],
        hoy_iso="2026-05-17",
        tiene_stock_ahora=False,
        historial={},
        producto="A",
        ventana_inicio_iso=None,
    )
    assert d == 20


def test_dias_con_stock_proxy_con_stock_ahora_hasta_hoy():
    # Con stock ahora -> primera venta .. hoy
    d = dias_con_stock(
        fechas_venta=["2026-05-15"],
        hoy_iso="2026-05-17",
        tiene_stock_ahora=True,
        historial={},
        producto="A",
        ventana_inicio_iso=None,
    )
    assert d == 3  # 15,16,17


def test_dias_con_stock_respeta_ventana_inicio():
    d = dias_con_stock(
        fechas_venta=["2026-01-01", "2026-05-16"],
        hoy_iso="2026-05-17",
        tiene_stock_ahora=True,
        historial={},
        producto="A",
        ventana_inicio_iso="2026-05-10",  # ventana reciente arranca acá
    )
    assert d == 8  # 10..17


def test_dias_con_stock_hibrido_descuenta_dias_sin_stock_por_snapshot():
    # Ventana 2026-05-10..2026-05-17 (8 días). Snapshot dice stock 0 los días 12 y 13.
    hist = {
        "2026-05-12": {"A": 0},
        "2026-05-13": {"A": 0},
        "2026-05-14": {"A": 5},
    }
    d = dias_con_stock(
        fechas_venta=["2026-05-10", "2026-05-16"],
        hoy_iso="2026-05-17",
        tiene_stock_ahora=True,
        historial=hist,
        producto="A",
        ventana_inicio_iso="2026-05-10",
    )
    # total 8, snapshot cubre 3 (12,13,14), con stock 1 (14). proxy = 8-3 = 5. total = 5+1 = 6
    assert d == 6


def test_dias_con_stock_sin_ventas_devuelve_1():
    d = dias_con_stock([], "2026-05-17", False, {}, "A", None)
    assert d == 1


from velocidad_restock import calcular_velocidad_restock

PARAMS = {
    "lead_time": 7, "colchon": 7, "cobertura": 30,
    "ventana_reciente": 90, "min_unidades_conf": 5, "min_dias_conf": 3,
}


def _df_items(rows):
    # rows: list de (fecha, [(prod, qty, costo), ...])
    data = []
    for fecha, items in rows:
        data.append({"Fecha": fecha, "Items": [
            {"producto": p, "cantidad": q, "costo": c} for p, q, c in items
        ]})
    return pd.DataFrame(data)


def test_producto_que_se_quiebra_tiene_vel_alta_y_pide_restock():
    # 8u entre 01/03 y 20/03, sin stock ahora -> vel ~ 8/20 = 0.4
    rows = [(f"2026-03-{d:02d}", [("Anbernic", 1, 100.0)]) for d in range(1, 21)
            if d in (1, 3, 5, 7, 9, 11, 13, 20)]  # 8 ventas
    df = _df_items(rows)
    out = calcular_velocidad_restock(
        df, stock_map={"Anbernic": 0}, historial={},
        precio_map={"Anbernic": 1000.0}, params=PARAMS, hoy_iso="2026-05-17",
    )
    r = out[out["Producto"] == "Anbernic"].iloc[0]
    assert round(r["Vel. reciente"], 2) >= 0.1  # no diluido por 229 días
    assert r["Restock sugerido"] > 0
    assert bool(r["_necesita_restock"]) is True


def test_producto_zombie_no_es_critico():
    # vendió hace 8 meses, nada reciente, ventana reciente 90d
    rows = [("2025-09-01", [("Viejo", 50, 10.0)])]
    df = _df_items(rows)
    out = calcular_velocidad_restock(
        df, stock_map={"Viejo": 0}, historial={},
        precio_map={"Viejo": 500.0}, params=PARAMS, hoy_iso="2026-05-17",
    )
    r = out[out["Producto"] == "Viejo"].iloc[0]
    assert r["Vel. reciente"] == 0
    assert bool(r["_necesita_restock"]) is False


def test_orden_multiproducto_cuenta_unidades_correctas():
    rows = [("2026-05-10", [("A", 2, 10.0), ("B", 1, 5.0)])]
    df = _df_items(rows)
    out = calcular_velocidad_restock(
        df, stock_map={"A": 0, "B": 0}, historial={},
        precio_map={"A": 100.0, "B": 100.0}, params=PARAMS, hoy_iso="2026-05-17",
    )
    a = out[out["Producto"] == "A"].iloc[0]
    b = out[out["Producto"] == "B"].iloc[0]
    assert a["Unidades"] == 2
    assert b["Unidades"] == 1


def test_baja_confianza_no_dispara_restock():
    rows = [("2026-05-10", [("Raro", 1, 10.0)])]  # 1 unidad, 1 día
    df = _df_items(rows)
    out = calcular_velocidad_restock(
        df, stock_map={"Raro": 0}, historial={},
        precio_map={"Raro": 100.0}, params=PARAMS, hoy_iso="2026-05-17",
    )
    r = out[out["Producto"] == "Raro"].iloc[0]
    assert r["Confianza"] == "baja"
    assert bool(r["_necesita_restock"]) is False


def test_orden_por_facturacion_en_riesgo_desc():
    rows = (
        [(f"2026-05-{d:02d}", [("Caro", 1, 10.0)]) for d in range(1, 11)] +
        [(f"2026-05-{d:02d}", [("Barato", 1, 10.0)]) for d in range(1, 11)]
    )
    df = _df_items(rows)
    out = calcular_velocidad_restock(
        df, stock_map={"Caro": 1, "Barato": 1}, historial={},
        precio_map={"Caro": 100000.0, "Barato": 100.0},
        params=PARAMS, hoy_iso="2026-05-17",
    )
    assert out.iloc[0]["Producto"] == "Caro"


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests OK")


if __name__ == "__main__":
    _run()
