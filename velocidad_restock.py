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
