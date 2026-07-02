# ⚠ GENERADO desde Market Gamer - Core (sync/sync.py) — NO editar aca.
# Fuente: lib/tn_client.py (Market Gamer - Core) · hash 4069f7e7f367

"""
tn_client — cliente HTTP de la API de Tienda Nube (store Market Gamer 6623036).

SOLO capa HTTP: auth, GET (suelto y paginado), PUT parcial, retry 429 con
Retry-After, timeouts. Los parsers de dominio viven en cada app (parse_producto
en el CRM, procesar_orders en el dashboard, etc.).

Semantica de errores (contratos historicos de los consumidores):
  - get(...)          devuelve el JSON parseado; levanta TNError si status >= 400
                      (tras agotar reintentos de 429). Errores de red propagan.
  - get_paginado(...) acumula paginas; si una pagina falla devuelve lo acumulado
                      (parcial), nunca levanta.
  - put(...)          devuelve (status, data) y NO levanta en 4xx/5xx.

Fuente unica: Market Gamer - Core (lib/tn_client.py). Las copias en cada app
son GENERADAS por sync.py — editar aca y correr python sync/sync.py.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

STORE_ID = "6623036"
BASE = f"https://api.tiendanube.com/v1/{STORE_ID}"
UA_DEFAULT = "MarketGamer (info@marketgamer.com.ar)"

_RETRY_429_ESPERA = 1.5   # segundos si TN no manda Retry-After
_RETRY_429_TOPE = 10.0    # nunca dormir mas que esto
_dormir = time.sleep      # inyectable en tests


def _retry_after(hdrs) -> float:
    """Retry-After del dict de headers, case-insensitive (dict(e.headers) pierde
    el lookup insensible de HTTPMessage). Default si falta o no parsea."""
    for k, v in hdrs.items():
        if k.lower() == "retry-after":
            try:
                return float(v)
            except (TypeError, ValueError):
                return _RETRY_429_ESPERA
    return _RETRY_429_ESPERA


class TNError(Exception):
    def __init__(self, status, data):
        super().__init__(f"TN {status}: {str(data)[:200]}")
        self.status = status
        self.data = data


def _http(method, url, headers, body=None, timeout=30):
    """Transporte real. Inyectable en tests via el parametro _http de get/put."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            cuerpo = e.read().decode("utf-8")
        except Exception:
            cuerpo = ""
        return e.code, dict(e.headers), cuerpo


def request(method, path, token=None, params=None, body=None, timeout=30,
            user_agent=None, reintentos_429=2, _http=_http):
    """(status, data) con retry de 429 respetando Retry-After (capado a 10s)."""
    tok = token or os.environ.get("TN_ACCESS_TOKEN", "")
    url = f"{BASE}/{path}"
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {
        "Authentication": f"bearer {tok}",
        "User-Agent": user_agent or UA_DEFAULT,
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    intento = 0
    while True:
        status, hdrs, texto = _http(method, url, headers, body=body, timeout=timeout)
        if status == 429 and intento < reintentos_429:
            intento += 1
            _dormir(min(max(_retry_after(hdrs), 0.0), _RETRY_429_TOPE))
            continue
        try:
            data = json.loads(texto) if texto else None
        except ValueError:
            data = {"raw": texto}
        return status, data


def get(path, token=None, params=None, timeout=30, user_agent=None, _http=_http):
    status, data = request("GET", path, token=token, params=params,
                           timeout=timeout, user_agent=user_agent, _http=_http)
    if status >= 400:
        raise TNError(status, data)
    return data


def get_paginado(path, params=None, per_page=200, max_pages=50, token=None,
                 timeout=30, user_agent=None, _http=_http):
    """Acumula paginas (1..max_pages); corta cuando una pagina trae menos de
    per_page. Si una pagina falla, devuelve lo acumulado (parcial)."""
    filas = []
    for page in range(1, max_pages + 1):
        p = dict(params or {})
        p["per_page"] = per_page
        p["page"] = page
        try:
            batch = get(path, token=token, params=p, timeout=timeout,
                        user_agent=user_agent, _http=_http)
        except Exception:
            break
        if not isinstance(batch, list):
            break
        filas.extend(batch)
        if len(batch) < per_page:
            break
    return filas


def put(path, body, token=None, timeout=30, user_agent=None, _http=_http):
    """(status, data). NO levanta NUNCA — ni en 4xx/5xx ni en errores de red
    (contrato historico de tn_write: la correccion masiva registra el error
    del item y sigue con el lote; un timeout no la corta)."""
    try:
        return request("PUT", path, token=token, body=body, timeout=timeout,
                       user_agent=user_agent, _http=_http)
    except Exception as e:
        return 0, {"error": str(e)}
