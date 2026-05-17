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
