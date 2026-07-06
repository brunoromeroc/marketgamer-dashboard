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


def compactar_historial(historial, max_dias_diario=180, hoy_iso=None):
    """Compacta el historial sin perder profundidad temporal.

    Las fechas dentro de los últimos `max_dias_diario` días se conservan a
    diario; las más viejas se compactan a una por semana ISO (se queda la
    primera fecha de cada semana). Así la curva de stock valuado crece de
    por vida con la sheet acotada. No muta el original.
    """
    if not historial:
        return {}
    fechas = sorted(historial.keys())
    if hoy_iso is None:
        hoy_iso = fechas[-1]
    corte = date.fromisoformat(hoy_iso) - timedelta(days=max_dias_diario)
    out = {}
    semanas_vistas = set()
    for f in fechas:
        d = date.fromisoformat(f)
        if d >= corte:
            out[f] = dict(historial[f])
        else:
            clave = (d.isocalendar()[0], d.isocalendar()[1])
            if clave not in semanas_vistas:
                semanas_vistas.add(clave)
                out[f] = dict(historial[f])
    return out


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
