"""
operacion.py — parsing puro de la respuesta GET /senales del worker.
Sin Streamlit: solo stdlib. Testeable en aislamiento (patrón velocidad_restock).
"""
from datetime import datetime, timezone

_FICHAS_KEYS = ("total", "rojas", "amarillas", "verdes", "sin_evaluar", "con_drift",
                "sin_peso", "propuestas_pendientes", "con_alerta_claims")
_CLIENTES_KEYS = ("total", "vip", "activo", "dormido", "inactivo", "gran_comprador")
_AUTO_KEYS = ("pendientes_tracking", "pendientes_review", "enviados_hoy", "limite_diario")


def edad_legible(ts_ms, ahora_ms=None):
    """'hace 5 min' / 'hace 3 h' / 'hace 2 dias' / 'sin datos'."""
    if not ts_ms:
        return "sin datos"
    ahora = ahora_ms if ahora_ms is not None else datetime.now(timezone.utc).timestamp() * 1000
    mins = max(0, int((ahora - ts_ms) / 60_000))
    if mins < 60:
        return f"hace {mins} min"
    horas = mins // 60
    if horas < 48:
        return f"hace {horas} h"
    return f"hace {horas // 24} dias"


def parse_senales(data):
    """Normaliza la respuesta del worker a un dict plano para las cards.
    Tolerante: claves ausentes → 0/None/[]; nunca levanta."""
    data = data or {}
    snap = data.get("snapshot") or {}
    fichas = snap.get("fichas") or {}
    clientes = snap.get("clientes") or {}
    autos = snap.get("automatizaciones") or {}
    merki = data.get("merki_7d") or {}
    return {
        "snapshot_ts": data.get("snapshot_ts"),
        "fichas": {k: fichas.get(k, 0) for k in _FICHAS_KEYS},
        "clientes": {k: clientes.get(k, 0) for k in _CLIENTES_KEYS},
        "automatizaciones": {k: autos.get(k, 0) for k in _AUTO_KEYS},
        "envio_habilitado": bool(autos.get("envio_habilitado")),
        "merki": {
            "total_messages": merki.get("total_messages", 0),
            "unique_sessions": merki.get("unique_sessions", 0),
            "lead_sessions": merki.get("lead_sessions", 0),
            "consultas": merki.get("consultas_recientes") or [],
        },
    }
