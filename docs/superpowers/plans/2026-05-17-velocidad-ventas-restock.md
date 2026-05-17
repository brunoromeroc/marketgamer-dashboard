# Rediseño Velocidad de ventas y restock — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reescribir la solapa "Velocidad de ventas" para que la velocidad se calcule sobre días con stock (proxy + snapshot diario), desacoplada del selector de período, con modelo de restock estándar y alertas accionables.

**Architecture:** La lógica pura (velocidad, días con stock, restock, merge/recorte de historial, explosión de líneas) vive en un módulo nuevo `velocidad_restock.py` (solo `pandas`/`datetime`, sin Streamlit) testeable en aislamiento. `app.py` agrega la columna `Items` en `procesar_orders`, el wrapper de I/O `gs_append_snapshot`, y reemplaza el cuerpo de la solapa para llamar a las funciones del módulo y renderizar.

**Tech Stack:** Python 3, pandas, Streamlit, gspread (I/O Google Sheets). Tests = scripts `python` con `assert` (el proyecto no usa pytest; no se agregan dependencias).

**Spec:** `docs/superpowers/specs/2026-05-17-velocidad-ventas-restock-design.md`

---

## File Structure

- **Create** `velocidad_restock.py` (raíz, junto a `app.py`) — lógica pura: `merge_snapshot`, `recortar_historial`, `explotar_items`, `dias_con_stock`, `calcular_velocidad_restock`. Solo importa `pandas` y `datetime`.
- **Create** `tests/test_velocidad_restock.py` — script de tests con `assert`, ejecutable con `python tests/test_velocidad_restock.py`.
- **Modify** `app.py`:
  - `procesar_orders` (~2021-2109): agregar columna `Items`.
  - Tras `gs_write` (~744): agregar `gs_append_snapshot`.
  - Stock tab (~3753): llamar `gs_append_snapshot` al cargar stock.
  - Solapa Velocidad (~3802-3946): reemplazar cuerpo por uso del módulo.

Convención de tipos (estable en todo el plan):
- `Items`: `list[dict]` con claves `"producto"` (str), `"cantidad"` (int), `"costo"` (float).
- `historial`: `dict[str, dict[str, int]]` → `{ "2026-05-17": {"Anbernic RG406H": 0, ...} }`.
- `stock_map`: `dict[str, int]` → `{producto: stock_actual}`.
- `precio_map`: `dict[str, float]` → `{producto: precio_unitario}`.
- `params`: `dict` con `lead_time, colchon, cobertura, ventana_reciente, min_unidades_conf, min_dias_conf` (ints).
- `hoy_iso`: `str` formato `"YYYY-MM-DD"`.

---

## Task 1: Crear módulo con `merge_snapshot` y `recortar_historial`

**Files:**
- Create: `velocidad_restock.py`
- Test: `tests/test_velocidad_restock.py`

- [ ] **Step 1: Write the failing test**

Crear `tests/test_velocidad_restock.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests OK")


if __name__ == "__main__":
    _run()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_velocidad_restock.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'velocidad_restock'`

- [ ] **Step 3: Write minimal implementation**

Crear `velocidad_restock.py`:

```python
"""Lógica pura de velocidad de ventas y planificación de restock.

Sin Streamlit: solo pandas y datetime. Testeable en aislamiento.
"""
from datetime import date, timedelta

import pandas as pd


def merge_snapshot(historial, fecha_iso, stock_map):
    """Agrega (o pisa, idempotente por fecha) el snapshot de stock de un día.

    No muta el dict original.
    """
    out = {f: dict(v) for f, v in historial.items()}
    out[fecha_iso] = dict(stock_map)
    return out


def recortar_historial(historial, max_dias=180):
    """Mantiene solo las últimas `max_dias` fechas (orden ISO ascendente)."""
    fechas = sorted(historial.keys())
    if len(fechas) <= max_dias:
        return {f: historial[f] for f in fechas}
    keep = fechas[-max_dias:]
    return {f: historial[f] for f in keep}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_velocidad_restock.py`
Expected: PASS — `5 tests OK`

- [ ] **Step 5: Commit**

```bash
git add velocidad_restock.py tests/test_velocidad_restock.py
git commit -m "feat(velocidad): modulo puro con merge_snapshot y recortar_historial"
```

---

## Task 2: `explotar_items` — long-form de líneas de venta

**Files:**
- Modify: `velocidad_restock.py`
- Test: `tests/test_velocidad_restock.py`

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_velocidad_restock.py` (antes de `_run`):

```python
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
```

`import pandas as pd` ya está implícito vía el módulo; agregar `import pandas as pd` al tope del test si no está. (Agregarlo: tras los `sys.path` inserts, añadir `import pandas as pd`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_velocidad_restock.py`
Expected: FAIL — `ImportError: cannot import name 'explotar_items'`

- [ ] **Step 3: Write minimal implementation**

Agregar a `velocidad_restock.py`:

```python
def explotar_items(df_tn):
    """Convierte df_tn (con columna Items) a long-form: una fila por línea de venta.

    Devuelve columnas: Fecha, Producto, Cantidad, Costo.
    """
    filas = []
    for _, row in df_tn.iterrows():
        items = row.get("Items")
        if not items:
            continue
        for it in items:
            filas.append({
                "Fecha": row.get("Fecha", ""),
                "Producto": it["producto"],
                "Cantidad": int(it["cantidad"]),
                "Costo": float(it["costo"]),
            })
    return pd.DataFrame(filas, columns=["Fecha", "Producto", "Cantidad", "Costo"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_velocidad_restock.py`
Expected: PASS — `7 tests OK`

- [ ] **Step 5: Commit**

```bash
git add velocidad_restock.py tests/test_velocidad_restock.py
git commit -m "feat(velocidad): explotar_items a long-form por linea de venta"
```

---

## Task 3: `dias_con_stock` — denominador híbrido proxy + snapshot

**Files:**
- Modify: `velocidad_restock.py`
- Test: `tests/test_velocidad_restock.py`

Regla (del spec): ventana `[inicio, fin]` donde `inicio` = primera venta del producto en la ventana de análisis, `fin` = `hoy` si tiene stock ahora (>0), si no la última venta. `total_dias = (fin - inicio).days + 1` (mín 1). Días cubiertos por snapshot dentro de la ventana = fechas del historial en `[inicio, fin]`; de esas, las que tienen `stock > 0` cuentan como con stock. Los días NO cubiertos por snapshot dentro de la ventana se asumen con stock (proxy). `dias_con_stock = dias_snapshot_con_stock + (total_dias - dias_snapshot_cubiertos)`, mínimo 1.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_velocidad_restock.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_velocidad_restock.py`
Expected: FAIL — `ImportError: cannot import name 'dias_con_stock'`

- [ ] **Step 3: Write minimal implementation**

Agregar a `velocidad_restock.py`:

```python
def _d(iso):
    return date.fromisoformat(iso)


def dias_con_stock(fechas_venta, hoy_iso, tiene_stock_ahora, historial,
                   producto, ventana_inicio_iso):
    """Días en que el producto estuvo disponible, dentro de la ventana de análisis.

    Híbrido: usa snapshot real donde exista, proxy (asume disponible) donde no.
    """
    fechas = sorted(f for f in fechas_venta if f)
    if not fechas:
        return 1

    inicio = _d(fechas[0])
    if ventana_inicio_iso:
        vi = _d(ventana_inicio_iso)
        if vi > inicio:
            inicio = vi

    fin = _d(hoy_iso) if tiene_stock_ahora else _d(fechas[-1])
    if fin < inicio:
        return 1

    total_dias = (fin - inicio).days + 1

    snap_cubiertos = 0
    snap_con_stock = 0
    for fecha_iso, mapa in historial.items():
        f = _d(fecha_iso)
        if inicio <= f <= fin:
            snap_cubiertos += 1
            if mapa.get(producto, 0) and mapa.get(producto, 0) > 0:
                snap_con_stock += 1

    proxy_dias = total_dias - snap_cubiertos
    return max(1, snap_con_stock + proxy_dias)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_velocidad_restock.py`
Expected: PASS — `12 tests OK`

- [ ] **Step 5: Commit**

```bash
git add velocidad_restock.py tests/test_velocidad_restock.py
git commit -m "feat(velocidad): dias_con_stock hibrido proxy + snapshot"
```

---

## Task 4: `calcular_velocidad_restock` — orquestación

**Files:**
- Modify: `velocidad_restock.py`
- Test: `tests/test_velocidad_restock.py`

Salida: DataFrame con columnas `Producto, Unidades, Vel. histórica, Vel. reciente, Stock actual, ROP, Días restantes, Restock sugerido, Facturación en riesgo, Confianza, _necesita_restock`, ordenado por `Facturación en riesgo` desc.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_velocidad_restock.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_velocidad_restock.py`
Expected: FAIL — `ImportError: cannot import name 'calcular_velocidad_restock'`

- [ ] **Step 3: Write minimal implementation**

Agregar a `velocidad_restock.py`:

```python
def calcular_velocidad_restock(df_tn, stock_map, historial, precio_map,
                                params, hoy_iso):
    """Calcula velocidad histórica/reciente, ROP, restock y riesgo por producto."""
    lt = params["lead_time"]
    colchon = params["colchon"]
    cobertura = params["cobertura"]
    vent = params["ventana_reciente"]
    min_u = params["min_unidades_conf"]
    min_d = params["min_dias_conf"]

    df_items = explotar_items(df_tn)
    hoy = _d(hoy_iso)
    corte_reciente = (hoy - timedelta(days=vent)).isoformat()

    filas = []
    for prod, g in df_items.groupby("Producto"):
        fechas_all = sorted(str(f) for f in g["Fecha"] if f)
        unid_hist = int(g["Cantidad"].sum())

        g_rec = g[g["Fecha"] >= corte_reciente]
        fechas_rec = sorted(str(f) for f in g_rec["Fecha"] if f)
        unid_rec = int(g_rec["Cantidad"].sum())

        stock_actual = stock_map.get(prod)
        sin_limite = stock_actual is None
        tiene_stock = (not sin_limite) and stock_actual > 0

        dias_hist = dias_con_stock(fechas_all, hoy_iso, tiene_stock,
                                   historial, prod, None)
        dias_rec = dias_con_stock(fechas_rec, hoy_iso, tiene_stock,
                                  historial, prod, corte_reciente)

        vel_hist = round(unid_hist / dias_hist, 3) if unid_hist else 0.0
        vel_rec = round(unid_rec / dias_rec, 3) if unid_rec else 0.0

        precio = float(precio_map.get(prod, 0) or 0)

        if vel_rec > 0 and not sin_limite:
            rop = round(vel_rec * lt + vel_rec * colchon, 2)
            dias_rest = round((stock_actual or 0) / vel_rec, 1)
            if (stock_actual or 0) <= rop:
                pedir = max(0, round(vel_rec * (lt + cobertura) - (stock_actual or 0)))
            else:
                pedir = 0
            dias_quiebre = max(0, lt - dias_rest)
            fact_riesgo = round(vel_rec * precio * dias_quiebre)
        else:
            rop = 0.0
            dias_rest = "—"
            pedir = 0
            fact_riesgo = 0

        dias_distintos = len(set(fechas_rec))
        confianza = "baja" if (unid_rec < min_u or dias_distintos < min_d) else "ok"
        necesita = (confianza == "ok") and pedir > 0

        filas.append({
            "Producto": prod,
            "Unidades": unid_rec,
            "Vel. histórica": vel_hist,
            "Vel. reciente": vel_rec,
            "Stock actual": "Sin límite" if sin_limite else (stock_actual if stock_actual is not None else "—"),
            "ROP": rop,
            "Días restantes": dias_rest,
            "Restock sugerido": pedir if pedir > 0 else "—",
            "Facturación en riesgo": fact_riesgo,
            "Confianza": confianza,
            "_necesita_restock": necesita,
        })

    df = pd.DataFrame(filas)
    if df.empty:
        return df
    return df.sort_values("Facturación en riesgo", ascending=False).reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_velocidad_restock.py`
Expected: PASS — `17 tests OK`

- [ ] **Step 5: Commit**

```bash
git add velocidad_restock.py tests/test_velocidad_restock.py
git commit -m "feat(velocidad): calcular_velocidad_restock con modelo ROP y riesgo"
```

---

## Task 5: Agregar columna `Items` en `procesar_orders`

**Files:**
- Modify: `app.py` (función `procesar_orders`, ~2021-2109)

- [ ] **Step 1: Construir la lista de items junto al loop de productos**

En `app.py`, en el loop `for p in o.get("products", []):` dentro de `procesar_orders` (~2026-2031), reemplazar:

```python
        for p in o.get("products", []):
            nombre = _extraer_nombre_producto(p.get("name", ""))
            prods.append(nombre)
            qty = int(p.get("quantity", 1) or 1)
            cost = float(p.get("cost", 0) or 0)
            costo_productos += cost * qty
```

por:

```python
        items_linea = []
        for p in o.get("products", []):
            nombre = _extraer_nombre_producto(p.get("name", ""))
            prods.append(nombre)
            qty = int(p.get("quantity", 1) or 1)
            cost = float(p.get("cost", 0) or 0)
            costo_productos += cost * qty
            items_linea.append({"producto": nombre, "cantidad": qty, "costo": cost})
```

- [ ] **Step 2: Agregar `Items` al dict de fila**

En el `filas.append({...})` (~2083-2108), agregar tras la línea `"Metodo raw": str(metodo),`:

```python
            "Metodo raw": str(metodo),
            "Items": items_linea,
```

- [ ] **Step 3: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat(velocidad): columna Items por linea en procesar_orders"
```

---

## Task 6: `gs_append_snapshot` y wiring al cargar stock

**Files:**
- Modify: `app.py` (tras `gs_write`, ~744; Stock tab, ~3753)

- [ ] **Step 1: Agregar el wrapper de I/O**

En `app.py`, inmediatamente después de la función `gs_write` (termina con `return False` en ~744), agregar:

```python
def gs_append_snapshot(stock_map):
    """Guarda el snapshot de stock de hoy en HistorialStock (idempotente por fecha)."""
    from velocidad_restock import merge_snapshot, recortar_historial
    try:
        hoy = date.today().isoformat()
        hist = gs_read("HistorialStock") or {}
        hist = merge_snapshot(hist, hoy, stock_map)
        hist = recortar_historial(hist, max_dias=180)
        return gs_write("HistorialStock", hist)
    except Exception:
        return False
```

(`date` ya está importado en app.py — usado en `_ga4_date_ranges`.)

- [ ] **Step 2: Llamar al snapshot al cargar stock**

En la Stock tab, tras `st.session_state.stock_tn = pd.DataFrame(stock_rows)` (~3753), agregar justo después:

```python
                    st.session_state.stock_tn = pd.DataFrame(stock_rows)
                    _snap_map = {}
                    for _r in stock_rows:
                        _sv = _r["Stock"]
                        if isinstance(_sv, (int, float)):
                            _snap_map[_r["Producto"]] = _snap_map.get(_r["Producto"], 0) + int(_sv)
                    gs_append_snapshot(_snap_map)
```

- [ ] **Step 3: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat(velocidad): gs_append_snapshot + captura diaria al cargar stock"
```

---

## Task 7: Reemplazar el cuerpo de la solapa Velocidad

**Files:**
- Modify: `app.py` (solapa `elif seccion == "🔥 Velocidad de ventas":`, ~3802-3946)

Objetivo: reemplazar el cálculo manual y el render por uso del módulo, desacoplado del selector de período (usa `st.session_state.df_tn` completo, no `df_tn` filtrado).

- [ ] **Step 1: Identificar el rango exacto a reemplazar**

Run: `python -c "import io; L=open('app.py',encoding='utf-8').read().splitlines(); print([i+1 for i,l in enumerate(L) if 'TAB 5: VELOCIDAD' in l or 'TAB 6: GASTOS' in l])"`
Expected: dos números de línea (inicio TAB5, inicio TAB6). El bloque a reemplazar va desde `elif seccion == "🔥 Velocidad de ventas":` hasta la línea anterior al banner `# TAB 6`.

- [ ] **Step 2: Reemplazar el cuerpo de la solapa**

Reemplazar todo el bloque desde `elif seccion == "🔥 Velocidad de ventas":` hasta (sin incluir) `    # ═══...` previo a `# TAB 6: GASTOS FIJOS` por:

```python
    elif seccion == "🔥 Velocidad de ventas":
        from velocidad_restock import calcular_velocidad_restock
        st.subheader("🔥 Velocidad de ventas y planificación de restock")

        df_full = st.session_state.get("df_tn")
        if df_full is None or df_full.empty:
            st.info("Buscá primero para ver los datos.")
        else:
            stock_map = {}
            precio_map = {}
            stock_df = st.session_state.get("stock_tn")
            if stock_df is not None:
                for _, srow in stock_df.iterrows():
                    pn = srow["Producto"]
                    sv = srow["Stock"]
                    if isinstance(sv, (int, float)):
                        stock_map[pn] = stock_map.get(pn, 0) + int(sv)
                    pr = srow.get("Precio ($)", 0)
                    if pr and pn not in precio_map:
                        precio_map[pn] = float(pr)

            historial = gs_read("HistorialStock") or {}

            with st.expander("⚙️ Configuración de alertas", expanded=False):
                ca, cb, cc = st.columns(3)
                p_lead = ca.slider("📦 Lead time (días)", 1, 45, 7)
                p_colchon = cb.slider("🛟 Colchón de seguridad (días)", 0, 30, 7)
                p_cob = cc.slider("🎯 Cobertura objetivo (días)", 7, 90, 30)
                cd, ce, cf = st.columns(3)
                p_vent = cd.slider("🕐 Ventana reciente (días)", 14, 180, 90)
                p_minu = ce.slider("Mín. unidades p/ confianza", 1, 20, 5)
                p_mind = cf.slider("Mín. días distintos p/ confianza", 1, 10, 3)

            params = {
                "lead_time": p_lead, "colchon": p_colchon, "cobertura": p_cob,
                "ventana_reciente": p_vent, "min_unidades_conf": p_minu,
                "min_dias_conf": p_mind,
            }

            df_vel = calcular_velocidad_restock(
                df_full, stock_map, historial, precio_map, params,
                date.today().isoformat(),
            )

            if df_vel.empty:
                st.info("No hay datos de productos.")
            else:
                df_ok = df_vel[df_vel["Confianza"] == "ok"]
                df_baja = df_vel[df_vel["Confianza"] == "baja"]
                criticos = df_ok[df_ok["_necesita_restock"]]

                v1, v2, v3, v4 = st.columns(4)
                v1.metric("Productos", len(df_vel))
                v2.metric("🔴 A reponer", len(criticos))
                v3.metric("Ventana reciente", f"{p_vent} días")
                v4.metric("Snapshots", len(historial))

                if not criticos.empty:
                    st.divider()
                    st.error(f"⚠️ {len(criticos)} producto(s) necesitan restock")
                    for _, crow in criticos.iterrows():
                        st.warning(
                            f"🔴 **{crow['Producto']}** — vel. reciente "
                            f"{crow['Vel. reciente']} u/día | stock {crow['Stock actual']} "
                            f"| ROP {crow['ROP']} | pedir **{crow['Restock sugerido']} u** "
                            f"| riesgo ${crow['Facturación en riesgo']:,.0f}"
                        )

                st.divider()
                df_chart = (df_ok[["Producto", "Vel. reciente"]]
                            .sort_values("Vel. reciente", ascending=True).tail(15))
                if not df_chart.empty:
                    fig_vel = px.bar(
                        df_chart, x="Vel. reciente", y="Producto", orientation="h",
                        title="Velocidad reciente (u/día)", color="Vel. reciente",
                        color_continuous_scale=["#00C49F", "#FFD700", "#FF5733"],
                        text="Vel. reciente",
                    )
                    fig_vel.update_layout(showlegend=False, coloraxis_showscale=False,
                                          yaxis={"categoryorder": "total ascending"})
                    fig_vel.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                    st.plotly_chart(fig_vel, use_container_width=True)

                cols_show = [
                    "Producto", "Unidades", "Vel. histórica", "Vel. reciente",
                    "Stock actual", "ROP", "Días restantes", "Restock sugerido",
                    "Facturación en riesgo",
                ]
                st.dataframe(
                    df_ok[cols_show].style.format({
                        "Vel. histórica": "{:.3f}", "Vel. reciente": "{:.3f}",
                        "ROP": "{:.1f}", "Facturación en riesgo": "${:,.0f}",
                    }),
                    use_container_width=True, hide_index=True,
                )

                if not df_baja.empty:
                    with st.expander(f"🔸 {len(df_baja)} productos de baja confianza (pocas ventas)", expanded=False):
                        st.dataframe(
                            df_baja[["Producto", "Unidades", "Vel. reciente", "Stock actual"]],
                            use_container_width=True, hide_index=True,
                        )

                st.divider()
                st.subheader("📈 Evolución de ventas")
                prod_sel = st.selectbox("Producto", df_vel["Producto"].tolist())
                if prod_sel:
                    df_evo = df_full[df_full["Productos"].str.contains(prod_sel, na=False, regex=False)]
                    if not df_evo.empty:
                        df_evo_g = df_evo.groupby("Fecha").agg(
                            Unidades=("Cantidad", "sum"), Revenue=("Total ($)", "sum"),
                        ).reset_index()
                        df_evo_g["Acumulado"] = df_evo_g["Unidades"].cumsum()
                        fig_evo = px.bar(df_evo_g, x="Fecha", y="Unidades",
                            title=f"Ventas diarias — {prod_sel}", color_discrete_sequence=["#009EE3"])
                        fig_evo.add_scatter(x=df_evo_g["Fecha"], y=df_evo_g["Acumulado"],
                            mode="lines+markers", name="Acumulado",
                            line=dict(color="#FFD700", width=2), yaxis="y2")
                        fig_evo.update_layout(
                            yaxis2=dict(overlaying="y", side="right", showgrid=False),
                            legend=dict(orientation="h"),
                        )
                        st.plotly_chart(fig_evo, use_container_width=True)

                st.download_button("⬇️ Descargar análisis",
                    df_vel[cols_show].to_csv(index=False).encode("utf-8"),
                    "restock_analysis.csv", "text/csv")
```

- [ ] **Step 3: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Smoke test de import del módulo**

Run: `python -c "from velocidad_restock import calcular_velocidad_restock, merge_snapshot, recortar_historial, explotar_items, dias_con_stock; print('imports OK')"`
Expected: `imports OK`

- [ ] **Step 5: Re-correr suite de tests del módulo**

Run: `python tests/test_velocidad_restock.py`
Expected: PASS — `17 tests OK`

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat(velocidad): solapa usa motor nuevo, desacoplada del periodo lateral"
```

---

## Task 8: Verificación manual en el dashboard

**Files:** ninguno (verificación)

- [ ] **Step 1: Levantar el dashboard**

Run: `streamlit run app.py`
Expected: arranca sin errores de import ni sintaxis.

- [ ] **Step 2: Checklist funcional en la solapa "🔥 Velocidad de ventas"**

- [ ] La solapa carga sin error aunque no se haya cargado stock (usa proxy, no rompe).
- [ ] Cargar stock desde la solapa "📦 Stock" y volver: aparece "Snapshots: 1" (o más).
- [ ] El selector de período lateral NO cambia los números de esta solapa.
- [ ] Un producto sin stock que vendió concentrado (ej. Anbernic RG406H) muestra `Vel. reciente` claramente mayor que `unidades/229`.
- [ ] Los críticos listados siempre tienen `Restock sugerido` > 0 (ninguno con "—").
- [ ] Los productos de pocas ventas caen en el expander de "baja confianza", no en alertas rojas.
- [ ] La tabla está ordenada por "Facturación en riesgo" descendente.
- [ ] Cambiar los sliders (lead time, colchón, cobertura, ventana) recalcula en vivo.

- [ ] **Step 3: Commit (si hubo ajustes durante la verificación)**

```bash
git add -A
git commit -m "fix(velocidad): ajustes de verificacion manual"
```

---

## Self-Review (completado por el autor del plan)

- **Cobertura del spec:**
  - Fix conteo por línea (H) → Task 5. ✓
  - Snapshot diario B + persistencia append + retención 180 → Tasks 1, 6. ✓
  - Velocidad histórica + reciente sobre días con stock (proxy + híbrido) → Tasks 3, 4. ✓
  - Modelo restock ROP + 3 perillas → Task 4, Task 7 (sliders). ✓
  - Alertas a+b+c (sin acción / baja confianza / ranking por riesgo) → Task 4 (`_necesita_restock`, `Confianza`, orden), Task 7 (render). ✓
  - Desacople del selector de período → Task 7 (usa `st.session_state.df_tn` completo). ✓
  - Edge cases (sin ventas, sin límite, multi-variante, historial vacío, div/0) → Tasks 3, 4 (guardas) + tests. ✓
  - Testing + ast.parse → suite en cada task + Steps de verificación de sintaxis. ✓
- **Placeholder scan:** sin TBD/TODO; todos los steps con código completo. ✓
- **Consistencia de tipos:** firmas `merge_snapshot`, `recortar_historial`, `explotar_items`, `dias_con_stock`, `calcular_velocidad_restock` idénticas entre definición (Tasks 1-4) y uso (Tasks 6-7). `params`/`historial`/`stock_map`/`precio_map` consistentes. ✓
