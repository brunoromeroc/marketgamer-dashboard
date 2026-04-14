import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
import time
import json
import re
import urllib.parse

# ── Config ─────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Dashboard Market Gamer", layout="wide")
st.title("🎮 Dashboard de Ventas - Market Gamer")

TN_TOKEN = st.secrets["TN_TOKEN"]
TN_STORE_ID = st.secrets["TN_STORE_ID"]
SHEET_ID = st.secrets.get("SHEET_ID", "1wY2KjSC8SX-nMQD7J43xrdSY0SgG8fJeL9d5I_02DdE")
GCP_CREDS = st.secrets.get("gcp_service_account", {})
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_KEY", "")

COLORES = ["#00C49F", "#009EE3", "#FFD700", "#FF5733", "#AA00FF", "#FF69B4"]

# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt(n):
    try:
        return f"${float(n):,.0f}".replace(",", ".")
    except:
        return "-"

def fmt_pct(n):
    return f"{n:.2f}%"

def _normalizar(s):
    # Colapsar espacios y eliminar espacios entre letras/números del modelo
    # ej: "RG 477M 12+256GB" → "rg477m 12+256gb"  (espacios dentro del modelo se quitan)
    s = re.sub(r'\s+', ' ', str(s).strip().lower())
    # Quitar espacios entre partes alfanuméricas del modelo (no entre modelo y variante)
    s = re.sub(r'([a-z\d])\s+([a-z\d])', r'\1\2', s)
    return s

# ── Brand catalog (fuente: catalogo_market_gamer.csv + modelos TN) ─────────────
BRAND_CATALOG = {
    # ── Anbernic (bare model keys) ──────────────────────────────────────────────
    "rgnano":"Anbernic","rg28xx":"Anbernic","rg34xx":"Anbernic","rg34xxsp":"Anbernic",
    "rg35xx":"Anbernic","rg35xx2024":"Anbernic","rg35xxplus":"Anbernic",
    "rg35xxh":"Anbernic","rg35xxsp":"Anbernic","rg35xxpro":"Anbernic",
    "rg40xxh":"Anbernic","rg40xxv":"Anbernic",
    "rgcube":"Anbernic","rgcubexx":"Anbernic",
    "rg351p":"Anbernic","rg353p":"Anbernic","rg353v":"Anbernic",
    "rg353vs":"Anbernic","rg353m":"Anbernic","rg353ps":"Anbernic",
    "rgarcd":"Anbernic","rgarcs":"Anbernic","rg503":"Anbernic",
    "rg405m":"Anbernic","rg405v":"Anbernic","rg505":"Anbernic",
    "rgds":"Anbernic","rgp01":"Anbernic","rgg01":"Anbernic",
    "rg556":"Anbernic","rg557":"Anbernic",
    "rg406v":"Anbernic","rg406h":"Anbernic",
    "rgslide":"Anbernic","rg476h":"Anbernic",
    "rg477m":"Anbernic","rg477v":"Anbernic",
    "rgvita":"Anbernic","rgvitapro":"Anbernic",
    "win600":"Anbernic","k101plus":"Anbernic",
    # ── Anbernic (con prefijo de marca — para TN y proveedores que lo incluyen) ─
    "anbernicrgnano":"Anbernic","anbernicrg28xx":"Anbernic",
    "anbernicrg34xx":"Anbernic","anbernicrg34xxsp":"Anbernic",
    "anbernicrg35xx":"Anbernic","anbernicrg35xx2024":"Anbernic",
    "anbernicrg35xxplus":"Anbernic","anbernicrg35xxh":"Anbernic",
    "anbernicrg35xxsp":"Anbernic","anbernicrg35xxpro":"Anbernic",
    "anbernicrg40xxh":"Anbernic","anbernicrg40xxv":"Anbernic",
    "anbernicrgcube":"Anbernic","anbernicrgcubexx":"Anbernic",
    "anbernicrg351p":"Anbernic","anbernicrg353p":"Anbernic",
    "anbernicrg353v":"Anbernic","anbernicrg353vs":"Anbernic",
    "anbernicrg353m":"Anbernic","anbernicrg353ps":"Anbernic",
    "anbernicrgarcd":"Anbernic","anbernicrgarcs":"Anbernic","anbernicrg503":"Anbernic",
    "anbernicrg405m":"Anbernic","anbernicrg405v":"Anbernic","anbernicrg505":"Anbernic",
    "anbernicrgds":"Anbernic","anbernicrgp01":"Anbernic",
    "anbernicrg556":"Anbernic","anbernicrg557":"Anbernic",
    "anbernicrg406v":"Anbernic","anbernicrg406h":"Anbernic",
    "anbernicrgslide":"Anbernic","anbernicrg476h":"Anbernic",
    "anbernicrg477m":"Anbernic","anbernicrg477v":"Anbernic",
    "anbernicrgvita":"Anbernic","anbernicrgvitapro":"Anbernic",
    # ── Powkiddy (bare) ─────────────────────────────────────────────────────────
    "rgb10x":"Powkiddy","rgb20s":"Powkiddy","rgb20pro":"Powkiddy",
    "rgb20sx":"Powkiddy","rgb30":"Powkiddy",
    "rgb10max3":"Powkiddy","rgb10max3pro":"Powkiddy",
    "v10":"Powkiddy","v20":"Powkiddy","v90":"Powkiddy","v90s":"Powkiddy",
    "x28":"Powkiddy","x35h":"Powkiddy","x35s":"Powkiddy",
    "x51":"Powkiddy","x55":"Powkiddy","x70":"Powkiddy","x39pro":"Powkiddy",
    "q20mini":"Powkiddy","q90":"Powkiddy",
    # ── Powkiddy (con prefijo) ───────────────────────────────────────────────────
    "powkiddyrgb10x":"Powkiddy","powkiddyrgb20s":"Powkiddy","powkiddyrgb20pro":"Powkiddy",
    "powkiddyrgb20sx":"Powkiddy","powkiddyrgb30":"Powkiddy",
    "powkiddyrgb10max3":"Powkiddy","powkiddyrgb10max3pro":"Powkiddy",
    "powkiddyv10":"Powkiddy","powkiddyv20":"Powkiddy",
    "powkiddyv90":"Powkiddy","powkiddyv90s":"Powkiddy",
    "powkiddyx28":"Powkiddy","powkiddyx35h":"Powkiddy","powkiddyx35s":"Powkiddy",
    "powkiddyx51":"Powkiddy","powkiddyx55":"Powkiddy","powkiddyx70":"Powkiddy",
    "powkiddyx39pro":"Powkiddy","powkiddyq20mini":"Powkiddy","powkiddyq90":"Powkiddy",
    # ── Miyoo (bare) ────────────────────────────────────────────────────────────
    "miyoominiv3":"Miyoo","miyoominiv4":"Miyoo",
    "miyoominiplus":"Miyoo","miniplus":"Miyoo",
    "miyoominiflip":"Miyoo","miniflip":"Miyoo",
    "miyooflipv2":"Miyoo","flipv2":"Miyoo",
    "miyooa30":"Miyoo",
    # ── Trimui (siempre con prefijo — "brick" solo es demasiado genérico) ────────
    "trimuimodels":"Trimui","trimuismart":"Trimui",
    "trimuismartpro":"Trimui","trimuismartpros":"Trimui",
    "trimuibrick":"Trimui","trimuibrickhammer":"Trimui",
    # ── Retroid (bare + con prefijo) ─────────────────────────────────────────────
    "pocket4":"Retroid","pocket4pro":"Retroid","pocket5":"Retroid",
    "pocket6":"Retroid","pocketg2":"Retroid","pocketminiv2":"Retroid",
    "pocketclassic":"Retroid","pocketflip2":"Retroid","flip2":"Retroid",
    "retroidpocket4":"Retroid","retroidpocket4pro":"Retroid","retroidpocket5":"Retroid",
    "retroidpocket6":"Retroid","retroidpocketg2":"Retroid","retroidpocketminiv2":"Retroid",
    "retroidpocketclassic":"Retroid","retroidpocketflip2":"Retroid",
    "retroidflip2":"Retroid","retroidg2":"Retroid",
}

def _get_brand(product_name: str) -> str:
    """Detecta la marca de un producto por nombre normalizado."""
    cleaned = re.sub(r'\s*\d+\+\d+\s*gb.*', '', product_name, flags=re.IGNORECASE).strip()
    norm = re.sub(r'[^a-z0-9]', '', cleaned.lower())
    return BRAND_CATALOG.get(norm, "—")

# ── Proveedores helpers ────────────────────────────────────────────────────────
from datetime import date as _date

def compute_catalog_diff(old_products: dict, new_products: dict) -> list:
    """Compara dos catálogos y devuelve lista de cambios (cambiado/nuevo/eliminado)."""
    diff = []
    old_keys = set(old_products.keys())
    new_keys = set(new_products.keys())
    for name in old_keys & new_keys:
        try:
            old_price = float(old_products[name].get("precio_usd", 0))
            new_price = float(new_products[name].get("precio_usd", 0))
        except (TypeError, ValueError):
            continue
        if abs(old_price - new_price) > 0.01:
            diff.append({
                "Producto": name,
                "Antes (USD)": old_price,
                "Después (USD)": new_price,
                "tipo": "cambiado",
            })
    for name in new_keys - old_keys:
        diff.append({
            "Producto": name,
            "Antes (USD)": None,
            "Después (USD)": float(new_products[name].get("precio_usd", 0)),
            "tipo": "nuevo",
        })
    for name in old_keys - new_keys:
        diff.append({
            "Producto": name,
            "Antes (USD)": float(old_products[name].get("precio_usd", 0)),
            "Después (USD)": None,
            "tipo": "eliminado",
        })
    return diff


def parse_pptx_catalog(file_bytes: bytes) -> list:
    """
    Extrae filas (Producto, FOB USD, Storage) de un PowerPoint de lista de precios.
    Soporta dos formatos:
    - Tablas (columnas: nombre, precio, storage)
    - Text boxes agrupados (ej. Powkiddy): "MODELO  NNpcs  STORAGE  $PRECIO"
    """
    import io, re as _re
    from pptx import Presentation
    rows = []
    seen = set()
    NS = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
    PRODUCT_RE = _re.compile(
        r'([A-Za-z][A-Za-z0-9 ]*?)\s+\d+\s*pcs\s+([^$]*?)\$\s*(\d+\.?\d*)',
        _re.IGNORECASE,
    )

    def _slide_xml_text(slide):
        parts = []
        for t in slide._element.iter(f'{NS}t'):
            if t.text and t.text.strip():
                parts.append(t.text.strip())
        return ' '.join(parts)

    try:
        prs = Presentation(io.BytesIO(file_bytes))
    except Exception:
        return []

    for slide in prs.slides:
        # ── Estrategia 1: tablas explícitas ──────────────────────────────────
        found_table = False
        for shape in slide.shapes:
            if not shape.has_table:
                continue
            found_table = True
            table = shape.table
            for row_idx in range(len(table.rows)):
                cells = [cell.text.strip() for cell in table.rows[row_idx].cells]
                for i, cell in enumerate(cells):
                    try:
                        val = float(cell.replace("$", "").replace(",", "").replace("USD", "").strip())
                        if not (1 < val < 5000):
                            continue
                        nombre_parts = [
                            c for c in cells[:i]
                            if c and len(c) > 2 and not c.replace(".", "").isdigit()
                        ]
                        if not nombre_parts:
                            continue
                        nombre = nombre_parts[0]
                        if nombre in seen:
                            break
                        seen.add(nombre)
                        storage = "—"
                        for c in cells:
                            if any(s in c.upper() for s in ["64G", "128G", "256G", "32G", "16G", "512G", "1TB"]):
                                storage = c.strip()
                                break
                        rows.append({"Producto": nombre, "FOB (USD)": val, "Marca": "—", "Pantalla": "—", "CPU": "—", "Storage": storage})
                        break
                    except ValueError:
                        continue

        if found_table:
            continue

        # ── Estrategia 2: text boxes agrupados (formato Powkiddy/Trimui) ────────
        # Estructura: "MODELO NNpcs STORAGE $PRECIO / / MODELO2 NNpcs STORAGE $PRECIO2"
        # Algunos slides no usan "/" como separador (ej. "X28 50pcs $93 X55 50pcs $48").
        # Algoritmo por marcador "NNpcs":
        #   - Nombre: en el segmento ANTERIOR al pcs, tomar texto después del último precio.
        #     Si no hay precio previo, tomar el último word-group (split en /  o espacios).
        #   - Precio: primer $XX en el segmento POSTERIOR al pcs (hasta el siguiente pcs).
        slide_text = _slide_xml_text(slide)
        PCS_ITER = list(_re.finditer(r'\d+\s*pcs', slide_text, _re.IGNORECASE))
        NAME_MAP = {"HAMMER": "Brick Hammer", "SMART PRO S": "Smart Pro S",
                    "SMART PRO": "Smart Pro", "SMART": "Smart"}
        TRIMUI_MODELS = {"Smart", "Smart Pro", "Smart Pro S", "Brick", "Brick Hammer"}

        for idx, pcs_m in enumerate(PCS_ITER):
            # Segmento anterior: desde el fin del pcs previo (o inicio) hasta este pcs
            prev_end = PCS_ITER[idx - 1].end() if idx > 0 else 0
            seg_before = slide_text[prev_end:pcs_m.start()]

            # Extraer nombre: texto después del último precio en seg_before
            last_price = list(_re.finditer(r'\$\s*\d+\.?\d*', seg_before))
            if last_price:
                name_raw = seg_before[last_price[-1].end():].strip()
            else:
                parts = _re.split(r'\s*/\s*|\s{3,}', seg_before.strip())
                name_raw = parts[-1].strip() if parts else ''

            # Limpiar el nombre de slashes, storage y noise
            name_raw = _re.sub(r'^[\s/]+', '', name_raw)  # slashes/espacios al inicio
            name_raw = _re.sub(r'\b\d+\s*GB\S*\b', '', name_raw, flags=_re.IGNORECASE).strip()
            name_raw = _re.sub(r'\s+', ' ', name_raw).strip()

            if not name_raw or len(name_raw) < 2:
                continue
            if _re.fullmatch(r'[\d/\s.]+', name_raw):
                continue

            # Segmento posterior: desde este pcs hasta el siguiente (para encontrar el precio)
            seg_end = PCS_ITER[idx + 1].start() if idx + 1 < len(PCS_ITER) else len(slide_text)
            seg_after = slide_text[pcs_m.end():seg_end]
            # Buscar precio con $ (ej. "$45") o sin $ si el catálogo lo omitió (ej. "28")
            price_m = _re.search(r'\$\s*(\d+\.?\d*)', seg_after)
            if not price_m:
                # Fallback: número suelto entre 5 y 999 que no sea parte de storage/dimensiones
                price_m = _re.search(
                    r'(?<![GB\d])(?<!\d)\b(\d{2,3}(?:\.\d)?)\b(?!\s*(?:GB|g\b|mm|kg|pcs|\d))',
                    seg_after, _re.IGNORECASE
                )
            if not price_m:
                continue  # producto genuinamente sin precio en este catálogo
            try:
                val = float(price_m.group(1))
            except ValueError:
                continue
            if not (1 < val < 5000):
                continue

            name = NAME_MAP.get(name_raw.upper(), name_raw)
            brand = "Trimui" if name in TRIMUI_MODELS else "Powkiddy"
            full_name = f"{brand} {name}"

            if full_name in seen:
                continue
            seen.add(full_name)

            storage_m = _re.search(r'(\d+\s*GB\S*)', seg_after, _re.IGNORECASE)
            storage = storage_m.group(1) if storage_m else "—"
            rows.append({"Producto": full_name, "FOB (USD)": val, "Marca": brand,
                         "Pantalla": "—", "CPU": "—", "Storage": storage})

    return rows


def fuzzy_group_products(suppliers: dict, threshold: float = 0.80) -> pd.DataFrame:
    """
    Agrupa productos similares de distintos proveedores usando difflib.
    Devuelve DataFrame con Producto | Proveedor1 | Proveedor2 | ...

    Nota: usa un algoritmo greedy — cada producto se asigna al primer grupo
    con similitud >= threshold. El orden de iteración afecta los resultados.
    Para los 3 proveedores de Market Gamer (catálogos pequeños), esto es suficiente.
    """
    from difflib import SequenceMatcher

    sup_names = list(suppliers.keys())
    all_items = []
    for sup_name in sup_names:
        for prod_name, prod_info in suppliers[sup_name].get("productos", {}).items():
            all_items.append({
                "supplier": sup_name,
                "name": prod_name,
                "price": float(prod_info.get("precio_usd", 0)),
            })

    if not all_items:
        return pd.DataFrame()

    # Agrupar por similitud de nombre
    groups: list[list] = []
    for item in all_items:
        matched = None
        for group in groups:
            rep = group[0]["name"]
            if SequenceMatcher(None, _normalizar(item["name"]), _normalizar(rep)).ratio() >= threshold:
                matched = group
                break
        if matched is None:
            groups.append([item])
        else:
            matched.append(item)

    rows = []
    for group in groups:
        canonical = group[0]["name"]
        row: dict = {"Producto": canonical}
        for sup in sup_names:
            match = next((x for x in group if x["supplier"] == sup), None)
            row[sup] = match["price"] if match else None
        rows.append(row)

    return pd.DataFrame(rows).sort_values("Producto")


@st.cache_data(ttl=300)
def get_stock_for_planner() -> dict:
    """
    Devuelve {nombre_producto: stock_total} consultando la API de TN.
    Stock None = sin límite configurado.
    TTL 5 min.
    """
    products = get_tn_products()
    stock_dict: dict = {}
    for p in products:
        nombre_raw = p.get("name", {})
        nombre = (
            nombre_raw.get("es", "") if isinstance(nombre_raw, dict) else str(nombre_raw)
        ).strip()
        if not nombre:
            continue
        # Si cualquier variante no tiene límite de stock, tratamos el producto como sin límite.
        # Así el planificador no lo marca como urgente.
        total = 0
        unlimited = False
        for v in p.get("variants", []):
            s = v.get("stock", None)
            if s is None:
                unlimited = True
                break
            total += int(s)
        stock_dict[nombre] = None if unlimited else total  # None = sin límite
    return stock_dict

# ── Google Sheets ──────────────────────────────────────────────────────────────
@st.cache_resource
def get_gsheet_client():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(dict(GCP_CREDS), scopes=scopes)
        return gspread.authorize(creds)
    except Exception:
        return None

def gs_read(sheet_name):
    try:
        gc = get_gsheet_client()
        if not gc or not SHEET_ID:
            return {}
        ws = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        data = ws.get_all_values()
        if len(data) >= 2 and data[1]:
            return json.loads(data[1][0])
        return {}
    except Exception:
        return {}

def gs_write(sheet_name, data_dict):
    try:
        gc = get_gsheet_client()
        if not gc or not SHEET_ID:
            return False
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(sheet_name)
        except Exception:
            ws = sh.add_worksheet(sheet_name, rows=10, cols=2)
        ws.clear()
        ws.update("A1", [["key"], [json.dumps(data_dict)]])
        return True
    except Exception:
        return False

# ── API Tienda Nube ────────────────────────────────────────────────────────────
def get_tn_headers():
    return {
        "Authentication": f"bearer {TN_TOKEN}",
        "User-Agent": "MarketGamerDashboard (info@marketgamer.com.ar)",
    }

def get_tn_orders(fecha_desde, fecha_hasta):
    headers = get_tn_headers()
    all_orders, seen_ids = [], set()
    combinaciones = [
        {"payment_status": "paid"},
        {"payment_status": "paid", "status": "archived"},
        {"payment_status": "paid", "status": "closed"},
    ]
    with st.spinner("Conectando con Tienda Nube..."):
        for filtros in combinaciones:
            page = 1
            while True:
                r = requests.get(
                    f"https://api.tiendanube.com/v1/{TN_STORE_ID}/orders",
                    headers=headers,
                    params={
                        "per_page": 50, "page": page,
                        "created_at_min": f"{fecha_desde}T00:00:00-03:00",
                        "created_at_max": f"{fecha_hasta}T23:59:59-03:00",
                        **filtros,
                    },
                )
                if r.status_code == 404:
                    break
                if r.status_code == 429:
                    time.sleep(3)
                    continue
                if r.status_code != 200:
                    break
                try:
                    data = r.json()
                except Exception:
                    break
                if not data:
                    break
                for o in data:
                    oid = o.get("id")
                    if oid not in seen_ids:
                        seen_ids.add(oid)
                        all_orders.append(o)
                if len(data) < 50:
                    break
                page += 1
    return all_orders

def get_tn_pagos(fecha_desde, fecha_hasta):
    headers = get_tn_headers()
    all_pagos, seen_ids = [], set()
    with st.spinner("Conectando con Pago Nube..."):
        page = 1
        while True:
            r = requests.get(
                f"https://api.tiendanube.com/v1/{TN_STORE_ID}/transactions",
                headers=headers,
                params={
                    "per_page": 50, "page": page,
                    "created_at_min": f"{fecha_desde}T00:00:00-03:00",
                    "created_at_max": f"{fecha_hasta}T23:59:59-03:00",
                },
            )
            if r.status_code in [404, 422]:
                break
            if r.status_code == 429:
                time.sleep(3)
                continue
            if r.status_code != 200:
                break
            try:
                data = r.json()
            except Exception:
                break
            if not data:
                break
            for p in data:
                pid = p.get("id")
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    all_pagos.append(p)
            if len(data) < 50:
                break
            page += 1
    return all_pagos

def get_tn_products():
    headers = get_tn_headers()
    all_products = []
    page = 1
    while True:
        r = requests.get(
            f"https://api.tiendanube.com/v1/{TN_STORE_ID}/products",
            headers=headers,
            params={"per_page": 50, "page": page},
        )
        if r.status_code != 200:
            break
        try:
            data = r.json()
        except Exception:
            break
        if not data:
            break
        all_products.extend(data)
        if len(data) < 50:
            break
        page += 1
    return all_products

# ── Tasas Pago Nube ────────────────────────────────────────────────────────────
PROC_BASE = 0.0329
IVA_FACTOR = 1.2600
PROC_EFECTIVO = PROC_BASE * IVA_FACTOR

CUOTAS_BASE = {
    1: 0.0, 2: 0.0606, 3: 0.0798, 6: 0.1552,
    12: 0.3104, 18: 0.4346, 24: 0.5432,
}

def tasa_pago_nube(metodo, cuotas):
    metodo = str(metodo).lower()
    if any(x in metodo for x in ["transfer", "wire", "account_money"]):
        return 0.0099 * IVA_FACTOR
    if any(x in metodo for x in ["debit", "debito", "modo"]):
        return PROC_EFECTIVO
    cuotas = int(cuotas or 1)
    opciones = sorted(CUOTAS_BASE.keys())
    cuotas_key = min(opciones, key=lambda x: abs(x - cuotas))
    costo_cuotas = CUOTAS_BASE.get(cuotas_key, 0.0) * IVA_FACTOR
    return PROC_EFECTIVO + costo_cuotas

# ── FOB defaults ───────────────────────────────────────────────────────────────
FOB_DEFAULTS = {
    "Anbernic RG 34XX 64GB":      {"fob_usd": 59.00,  "peso_kg": 0.3400},
    "Anbernic RG 34XX SP 64GB":   {"fob_usd": 66.00,  "peso_kg": 0.3000},
    "Anbernic RG 35XX Pro 64GB":  {"fob_usd": 49.00,  "peso_kg": 0.3450},
    "Anbernic RG 35XX SP 64GB":   {"fob_usd": 49.00,  "peso_kg": 0.3300},
    "Anbernic RG 406H":           {"fob_usd": 136.34, "peso_kg": 0.4652},
    "Anbernic RG 406V":           {"fob_usd": 139.70, "peso_kg": 0.4900},
    "Anbernic RG 40XX H 64GB":    {"fob_usd": 47.30,  "peso_kg": 0.3730},
    "Anbernic RG 477M 128GB":     {"fob_usd": 284.00, "peso_kg": 0.6400},
    "Anbernic RG 557 128GB":      {"fob_usd": 264.00, "peso_kg": 0.6070},
    "Anbernic RG Cube 128GB":     {"fob_usd": 164.00, "peso_kg": 0.4630},
    "Anbernic RG Cube XX 64GB":   {"fob_usd": 59.00,  "peso_kg": 0.4430},
    "Anbernic RG P01 Blanco":     {"fob_usd": 12.70,  "peso_kg": 0.4300},
    "Anbernic RG P01 Negro":      {"fob_usd": 12.70,  "peso_kg": 0.4300},
    "Anbernic RG Slide 128GB":    {"fob_usd": 174.00, "peso_kg": 0.6500},
    "Anbernic RG40XX H":          {"fob_usd": 50.60,  "peso_kg": 0.3600},
    "Anbernic RG40XX V":          {"fob_usd": 48.40,  "peso_kg": 0.3700},
    "Miyoo A30":                  {"fob_usd": 34.50,  "peso_kg": 0.2200},
    "Miyoo Flip":                 {"fob_usd": 60.00,  "peso_kg": 0.2800},
    "Miyoo Mini Plus":            {"fob_usd": 40.00,  "peso_kg": 0.2700},
    "Powkiddy MAX3":              {"fob_usd": 48.00,  "peso_kg": 0.3800},
    "Powkiddy MAX3 Pro":          {"fob_usd": 90.00,  "peso_kg": 0.5000},
    "Powkiddy RGB10X":            {"fob_usd": 30.00,  "peso_kg": 0.3000},
    "Powkiddy RGB20 Pro":         {"fob_usd": 45.00,  "peso_kg": 0.3800},
    "Powkiddy RGB20S":            {"fob_usd": 32.00,  "peso_kg": 0.3500},
    "Powkiddy RGB20SX":           {"fob_usd": 48.00,  "peso_kg": 0.3800},
    "Powkiddy V10":               {"fob_usd": 28.00,  "peso_kg": 0.3000},
    "Powkiddy V20 16GB":          {"fob_usd": 33.00,  "peso_kg": 0.3500},
    "Powkiddy V90S 16GB":         {"fob_usd": 33.00,  "peso_kg": 0.3000},
    "Powkiddy X35H 16GB":         {"fob_usd": 40.00,  "peso_kg": 0.3500},
    "Powkiddy X35s":              {"fob_usd": 45.00,  "peso_kg": 0.3500},
    "R36S Dual":                  {"fob_usd": 21.50,  "peso_kg": 0.3200},
    "Trimui Brick":               {"fob_usd": 51.00,  "peso_kg": 0.3350},
    "Trimui Brick Hammer":        {"fob_usd": 60.00,  "peso_kg": 0.4000},
    "Trimui Smart":               {"fob_usd": 31.50,  "peso_kg": 0.1400},
    "Trimui Smart Pro":           {"fob_usd": 54.00,  "peso_kg": 0.4050},
}

def get_fob_usd(nombre_prod, costos_gs=None):
    nombre_norm = _normalizar(nombre_prod)
    if not nombre_norm:
        return 0.0
    candidatos = []
    if costos_gs:
        for k, v in costos_gs.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict):
                fob = float(v.get("fob_usd", 0) or 0)
                if fob > 0:
                    candidatos.append((_normalizar(k), fob))
    for k, v in FOB_DEFAULTS.items():
        candidatos.append((_normalizar(k), float(v.get("fob_usd", 0) or 0)))
    for k_norm, fob in candidatos:
        if k_norm == nombre_norm:
            return fob
    for k_norm, fob in candidatos:
        if k_norm in nombre_norm:
            return fob
    for k_norm, fob in candidatos:
        if nombre_norm in k_norm:
            return fob
    return 0.0

def get_costo_total_usd(nombre_prod, costos_gs=None):
    """Retorna costo total USD (FOB + import) desde costos guardados."""
    nombre_norm = _normalizar(nombre_prod)
    if not nombre_norm:
        return 0.0
    if costos_gs:
        for k, v in costos_gs.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict) and _normalizar(k) == nombre_norm:
                ct = float(v.get("costo_total_usd", 0) or 0)
                if ct > 0:
                    return ct
                fob = float(v.get("fob_usd", 0) or 0)
                peso = float(v.get("peso_kg", 0) or 0)
                ckg = float(costos_gs.get("_costo_kg_usd", 65.0) or 65.0)
                return fob + peso * ckg
    # Fallback a FOB_DEFAULTS
    for k, v in FOB_DEFAULTS.items():
        if _normalizar(k) == nombre_norm:
            fob = float(v.get("fob_usd", 0) or 0)
            peso = float(v.get("peso_kg", 0) or 0)
            return fob + peso * 65.0
    return 0.0

def calcular_costo_orden_ars(productos_str, cantidad, tipo_cambio_ars, costos_gs=None):
    prods = [p.strip() for p in str(productos_str).split(" / ") if p.strip()]
    if not prods:
        return 0.0
    if len(prods) == 1:
        return get_fob_usd(prods[0], costos_gs) * int(cantidad or 1) * tipo_cambio_ars
    return sum(get_fob_usd(p, costos_gs) * tipo_cambio_ars for p in prods)

def calcular_costo_total_orden_ars(productos_str, cantidad, tipo_cambio_ars, costos_gs=None):
    """Calcula costo total (FOB + import) en ARS."""
    prods = [p.strip() for p in str(productos_str).split(" / ") if p.strip()]
    if not prods:
        return 0.0
    if len(prods) == 1:
        return get_costo_total_usd(prods[0], costos_gs) * int(cantidad or 1) * tipo_cambio_ars
    return sum(get_costo_total_usd(p, costos_gs) * tipo_cambio_ars for p in prods)

def costo_final_row(row, tipo_cambio, costos_gs):
    costo_tn = float(row.get("Costo Productos ($)", 0) or 0)
    if costo_tn > 0:
        return round(costo_tn, 0)
    return round(calcular_costo_orden_ars(
        row.get("Productos", ""), row.get("Cantidad", 1), tipo_cambio, costos_gs
    ), 0)

def costo_total_final_row(row, tipo_cambio, costos_gs):
    """Costo total (FOB + import) para la fila."""
    return round(calcular_costo_total_orden_ars(
        row.get("Productos", ""), row.get("Cantidad", 1), tipo_cambio, costos_gs
    ), 0)

# ── Dólar blue ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_dolar_blue():
    try:
        r = requests.get("https://api.bluelytics.com.ar/v2/latest", timeout=5)
        if r.status_code == 200:
            return float(r.json()["blue"]["value_sell"])
    except Exception:
        pass
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=5)
        if r.status_code == 200:
            return float(r.json().get("venta", 0))
    except Exception:
        pass
    return None

# ── Procesamiento de datos ─────────────────────────────────────────────────────
def _extraer_nombre_producto(n):
    if isinstance(n, str):
        return n
    if isinstance(n, dict):
        return n.get("es", "") or next(iter(n.values()), "")
    return ""

def procesar_orders(orders):
    filas = []
    for o in orders:
        prods = []
        costo_productos = 0.0
        for p in o.get("products", []):
            nombre = _extraer_nombre_producto(p.get("name", ""))
            prods.append(nombre)
            qty = int(p.get("quantity", 1) or 1)
            cost = float(p.get("cost", 0) or 0)
            costo_productos += cost * qty
        productos = " / ".join(prods)
        cantidad = sum(int(p.get("quantity", 1) or 1) for p in o.get("products", []))

        pd_raw = o.get("payment_details", {})
        gateway = str(o.get("gateway", "")).lower()
        metodo = gateway
        cuotas = 1
        if isinstance(pd_raw, dict):
            metodo = pd_raw.get("method", gateway)
            cuotas = int(pd_raw.get("installments", 1) or 1)

        if metodo == "credit_card":
            label_medio = "Credito contado" if cuotas == 1 else f"Credito {cuotas} cuotas"
        elif metodo == "debit_card":
            label_medio = "Debito"
        elif any(x in str(metodo).lower() for x in ["transfer", "wire"]):
            label_medio = "Transferencia"
        elif "account_money" in str(metodo).lower():
            label_medio = "Dinero en cuenta"
        else:
            label_medio = str(metodo).replace("_", " ").title() if metodo else str(gateway)

        try:
            fecha = pd.to_datetime(o.get("created_at", "")).strftime("%Y-%m-%d")
        except Exception:
            fecha = ""

        total = float(o.get("total", 0))
        descuento = float(o.get("discount", 0) or 0)
        costo_envio_dueno = float(o.get("shipping_cost_owner", 0) or 0)
        tasa = tasa_pago_nube(metodo, cuotas)
        comision_pn = round(total * tasa, 2)
        neto = round(total - comision_pn, 2)
        margen = round(neto - costo_productos - costo_envio_dueno, 2)
        margen_pct = round((margen / total * 100) if total > 0 else 0, 2)

        filas.append({
            "Orden": o.get("number"),
            "Fecha": fecha,
            "Cliente": str(o.get("contact_name", "")),
            "Medio de Pago": label_medio,
            "Cuotas": cuotas,
            "Total ($)": total,
            "Descuento ($)": descuento,
            "Envio costo ($)": costo_envio_dueno,
            "Comision PN ($)": comision_pn,
            "Costo PN (%)": round(tasa * 100, 2),
            "Neto cobrado ($)": neto,
            "Costo Productos ($)": round(costo_productos, 2),
            "Margen ($)": margen,
            "Margen (%)": margen_pct,
            "Estado Envio": o.get("shipping_status", ""),
            "Productos": productos,
            "Cantidad": cantidad,
            "Canal": str(o.get("app_id", "") or "tiendanube"),
            "Estado": o.get("status", ""),
        })
    return pd.DataFrame(filas)

def procesar_pagos_pn(pagos):
    filas = []
    for p in pagos:
        try:
            fecha = pd.to_datetime(p.get("created_at", "")).strftime("%Y-%m-%d")
        except Exception:
            fecha = ""
        filas.append({
            "ID": str(p.get("id", "")),
            "Fecha": fecha,
            "Estado": p.get("status", ""),
            "Método": p.get("payment_method", ""),
            "Cuotas": p.get("installments", 1),
            "Monto ($)": float(p.get("amount", 0) or 0),
            "Fee ($)": float(p.get("fee_amount", 0) or p.get("fee", 0) or 0),
            "Neto ($)": float(p.get("net_amount", 0) or 0),
            "Orden TN": str(p.get("order_id", "")),
        })
    return pd.DataFrame(filas) if filas else pd.DataFrame()

def calcular_tasas_reales(df_pagos):
    if df_pagos.empty or "Fee ($)" not in df_pagos.columns:
        return None
    df_con_fee = df_pagos[df_pagos["Fee ($)"] > 0]
    if df_con_fee.empty:
        return None
    tasas = {}
    for metodo, grupo in df_con_fee.groupby("Método"):
        monto_total = grupo["Monto ($)"].sum()
        fee_total = grupo["Fee ($)"].sum()
        if monto_total > 0:
            tasas[metodo] = round(fee_total / monto_total * 100, 2)
    return tasas if tasas else None

# ── Session state init ─────────────────────────────────────────────────────────
defaults = {
    "df_tn": None, "df_pagos": None, "orders_raw": [],
    "costos_productos": {}, "ordenes_efectivo": set(), "ids_venta_local": set(),
}
for key, default in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Session state for pauta (so it persists across tab switches)
if "pauta_manual" not in st.session_state:
    st.session_state.pauta_manual = 0
if "pct_iva" not in st.session_state:
    st.session_state.pct_iva = 10.5
if "tipo_cambio_sf" not in st.session_state:
    st.session_state.tipo_cambio_sf = None

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📅 Período")
    periodo = st.radio("Seleccionar período", ["Este mes", "Mes anterior", "Esta semana", "Personalizado"], index=0)
    hoy = date.today()
    if periodo == "Este mes":
        fecha_desde = hoy.replace(day=1)
        fecha_hasta = hoy
    elif periodo == "Mes anterior":
        primer_dia = hoy.replace(day=1)
        fecha_hasta = primer_dia - timedelta(days=1)
        fecha_desde = fecha_hasta.replace(day=1)
    elif periodo == "Esta semana":
        fecha_desde = hoy - timedelta(days=hoy.weekday())
        fecha_hasta = hoy
    else:
        fecha_desde = st.date_input("Desde", value=hoy.replace(day=1))
        fecha_hasta = st.date_input("Hasta", value=hoy)

    if periodo != "Personalizado":
        st.info(f"📆 {fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')}")
    buscar = st.button("🔍 Buscar", use_container_width=True)

# ── Búsqueda ───────────────────────────────────────────────────────────────────
if buscar:
    orders = get_tn_orders(fecha_desde, fecha_hasta)
    if orders:
        orders_filtrados = []
        for o in orders:
            try:
                dt = pd.to_datetime(o.get("created_at", ""))
                if dt.tzinfo:
                    dt = dt.tz_convert(None)
                if fecha_desde <= dt.date() <= fecha_hasta:
                    orders_filtrados.append(o)
            except Exception:
                orders_filtrados.append(o)
        orders = orders_filtrados
        st.session_state.df_tn = procesar_orders(orders)
        st.session_state.orders_raw = orders
        st.success(f"✅ {len(orders)} órdenes cargadas desde Tienda Nube")
    else:
        st.session_state.df_tn = pd.DataFrame()
        st.session_state.orders_raw = []
        st.info("No se encontraron órdenes en el período.")

    pagos = get_tn_pagos(fecha_desde, fecha_hasta)
    st.session_state.df_pagos = procesar_pagos_pn(pagos) if pagos else pd.DataFrame()
    st.session_state.ordenes_efectivo = set()
    st.session_state.ids_venta_local = set()

# ── TABS ───────────────────────────────────────────────────────────────────────
dolar_blue = get_dolar_blue()

if st.session_state.df_tn is not None:
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
        "📊 Dashboard",
        "🔍 Detalle y ajustes",
        "💚 Salud Financiera",
        "📦 Stock",
        "🔥 Velocidad de ventas",
        "🏗️ Gastos fijos",
        "💻 Costos de consolas",
        "📐 Margen teórico",
        "📈 Margen real",
        "🏭 Proveedores",
        "🤖 Analista IA",
    ])
    df_tn = st.session_state.df_tn.copy()
    df_pagos = st.session_state.df_pagos.copy() if st.session_state.df_pagos is not None else pd.DataFrame()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1: DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════
    with tab1:
        st.subheader("🛍️ Tienda Nube")
        if df_tn.empty:
            st.info("No hay órdenes en este período.")
        else:
            # ── Costo ponderado de comisión PN ──
            total_facturado = df_tn["Total ($)"].sum()
            total_comision = df_tn["Comision PN ($)"].sum()
            costo_ponderado_pn = round(total_comision / total_facturado * 100, 2) if total_facturado > 0 else 0

            k1, k2, k3, k4, k5, k6 = st.columns(6)
            k1.metric("Ordenes", len(df_tn))
            k2.metric("Facturación bruta", fmt(total_facturado))
            k3.metric("Comisión PN", fmt(total_comision))
            k4.metric("Neto cobrado", fmt(df_tn["Neto cobrado ($)"].sum()))
            k5.metric(
                "Margen total",
                fmt(df_tn["Margen ($)"].sum()),
                help="⚠️ Usa el campo 'cost' de TN (puede estar en 0). Para margen real usá la solapa Salud Financiera.",
            )
            k6.metric(
                "Costo PN ponderado",
                f"{costo_ponderado_pn:.2f}%",
                help="Comisión total PN / Facturación bruta. Promedio real ponderado por monto.",
            )

            st.caption(
                "ℹ️ **Margen total**: se calcula como Neto cobrado − Costo productos (campo `cost` de TN) − Envío. "
                "Si no cargaste costos en TN, el margen aparece inflado. "
                "Usá la solapa **💚 Salud Financiera** para el margen real con costos FOB."
            )

            # ── Ventas por día (LÍNEA) + Top 10 por unidades ──
            col_a, col_b = st.columns(2)
            with col_a:
                df_dia = df_tn.groupby("Fecha")["Total ($)"].sum().reset_index()
                fig_dia = px.line(
                    df_dia, x="Fecha", y="Total ($)",
                    title="Ventas por día",
                    markers=True,
                    color_discrete_sequence=["#009EE3"],
                )
                fig_dia.update_layout(yaxis_tickformat="$,.0f")
                fig_dia.update_traces(
                    line=dict(width=3),
                    marker=dict(size=8),
                    fill="tozeroy",
                    fillcolor="rgba(0, 158, 227, 0.1)",
                )
                st.plotly_chart(fig_dia, use_container_width=True)

            with col_b:
                top_prods = {}
                for _, row in df_tn.iterrows():
                    for p in str(row.get("Productos", "")).split(" / "):
                        p = p.strip()
                        if p:
                            top_prods[p] = top_prods.get(p, 0) + int(row.get("Cantidad", 1))
                if top_prods:
                    df_tp = pd.DataFrame(list(top_prods.items()), columns=["Producto", "Unidades"])
                    df_tp = df_tp.sort_values("Unidades", ascending=False).head(10)
                    fig_tp = px.bar(
                        df_tp, x="Unidades", y="Producto", orientation="h",
                        title="Top 10 productos (unidades)",
                        color="Unidades",
                        color_continuous_scale=["#00C49F", "#009EE3"],
                        text="Unidades",
                    )
                    fig_tp.update_layout(
                        yaxis={"categoryorder": "total ascending"},
                        coloraxis_showscale=False,
                        margin=dict(l=10, r=10),
                    )
                    fig_tp.update_traces(textposition="outside", textfont_size=13)
                    st.plotly_chart(fig_tp, use_container_width=True)

            # ── Top 10 por facturación + Pie comisiones ──
            st.divider()
            col_rev1, col_rev2 = st.columns(2)
            with col_rev1:
                top_revenue = {}
                for _, row in df_tn.iterrows():
                    prods_list = [p.strip() for p in str(row.get("Productos", "")).split(" / ") if p.strip()]
                    n_prods = max(len(prods_list), 1)
                    for p in prods_list:
                        top_revenue[p] = top_revenue.get(p, 0) + row.get("Total ($)", 0) / n_prods
                if top_revenue:
                    df_rev = pd.DataFrame(list(top_revenue.items()), columns=["Producto", "Monto ($)"])
                    df_rev["Monto ($)"] = df_rev["Monto ($)"].round(0)
                    df_rev = df_rev.sort_values("Monto ($)", ascending=False).head(10)
                    fig_rev = px.bar(
                        df_rev, x="Monto ($)", y="Producto", orientation="h",
                        title="Top 10 productos (facturación $)",
                        color="Monto ($)",
                        color_continuous_scale=["#FFD700", "#FF5733"],
                        text="Monto ($)",
                    )
                    fig_rev.update_layout(
                        yaxis={"categoryorder": "total ascending"},
                        xaxis_tickformat="$,.0f",
                        coloraxis_showscale=False,
                        margin=dict(l=10, r=10),
                    )
                    fig_rev.update_traces(texttemplate="$%{x:,.0f}", textposition="outside", textfont_size=13)
                    st.plotly_chart(fig_rev, use_container_width=True)

            with col_rev2:
                # ── Pie chart comisiones por medio de pago ──
                comis_medio = df_tn.groupby("Medio de Pago").agg(
                    Ordenes=("Orden", "count"),
                    Facturacion=("Total ($)", "sum"),
                    Comision=("Comision PN ($)", "sum"),
                ).reset_index().sort_values("Comision", ascending=False)
                comis_medio["Costo %"] = (comis_medio["Comision"] / comis_medio["Facturacion"] * 100).round(2)

                fig_pie_com = px.pie(
                    comis_medio, names="Medio de Pago", values="Comision",
                    title="Comisiones PN por medio de pago",
                    color_discrete_sequence=COLORES,
                    hole=0.35,
                )
                fig_pie_com.update_traces(
                    textinfo="label+value+percent",
                    texttemplate="<b>%{label}</b><br>$%{value:,.0f}<br>(%{percent})",
                    textfont_size=12,
                    pull=[0.03] * len(comis_medio),
                )
                fig_pie_com.update_layout(showlegend=False)
                st.plotly_chart(fig_pie_com, use_container_width=True)

            # ── Transacciones por medio de pago ──
            st.divider()
            col_tx1, col_tx2 = st.columns(2)
            with col_tx1:
                tx_medio = df_tn.groupby("Medio de Pago")["Orden"].count().reset_index()
                tx_medio.columns = ["Medio de Pago", "Transacciones"]
                tx_medio = tx_medio.sort_values("Transacciones", ascending=False)
                fig_tx = px.bar(tx_medio, x="Medio de Pago", y="Transacciones",
                    title="Transacciones por medio de pago",
                    color_discrete_sequence=["#009EE3"], text="Transacciones")
                fig_tx.update_traces(textposition="outside")
                st.plotly_chart(fig_tx, use_container_width=True)

            with col_tx2:
                # Tabla resumen comisiones
                comis_fmt = comis_medio.copy()
                comis_fmt["Facturacion"] = comis_fmt["Facturacion"].apply(fmt)
                comis_fmt["Comision"] = comis_fmt["Comision"].apply(fmt)
                comis_fmt["Costo %"] = comis_fmt["Costo %"].apply(fmt_pct)
                comis_fmt.columns = ["Medio de Pago", "Órdenes", "Facturación", "Comisión PN", "Costo %"]
                st.markdown("**Detalle comisiones por medio de pago**")
                st.dataframe(comis_fmt, use_container_width=True, hide_index=True)
                st.caption(f"📊 **Costo ponderado total PN: {costo_ponderado_pn:.2f}%** (comisión real promedio sobre facturación)")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2: DETALLE Y AJUSTES
    # ══════════════════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("🛍️ Detalle de órdenes — Tienda Nube")
        if df_tn.empty:
            st.info("No hay órdenes en este período.")
        else:
            _dolar_det = dolar_blue or 1200
            _costos_gs = gs_read("CostosConsolas") or {}
            df_det = df_tn.copy()

            df_det["Costo Productos ($)"] = df_det.apply(
                lambda r: costo_final_row(r, _dolar_det, _costos_gs), axis=1
            )
            df_det["Neto cobrado ($)"] = df_det["Total ($)"] - df_det["Comision PN ($)"]
            df_det["Margen ($)"] = (
                df_det["Neto cobrado ($)"] - df_det["Costo Productos ($)"]
                - df_det["Envio costo ($)"].fillna(0)
            ).round(2)
            df_det["Margen (%)"] = df_det.apply(
                lambda r: round((r["Margen ($)"] / r["Total ($)"] * 100) if r["Total ($)"] > 0 else 0, 2), axis=1
            )

            cols_tn = [
                "Orden", "Fecha", "Cliente", "Medio de Pago", "Cuotas", "Total ($)",
                "Descuento ($)", "Envio costo ($)", "Comision PN ($)", "Costo PN (%)",
                "Neto cobrado ($)", "Costo Productos ($)", "Margen ($)", "Margen (%)",
                "Estado Envio", "Productos", "Cantidad", "Canal",
            ]
            cols_tn = [c for c in cols_tn if c in df_det.columns]

            def _color_margen_row(row):
                styles = [""] * len(row)
                if "Margen ($)" in row.index:
                    idx = list(row.index).index("Margen ($)")
                    if float(row["Margen ($)"]) >= 0:
                        styles[idx] = "background-color: #1e4620; color: white"
                    else:
                        styles[idx] = "background-color: #4a1010; color: white"
                return styles

            sin_costo_tn = int((df_det["Costo Productos ($)"] == 0).sum())
            caption_txt = f"💵 Tipo de cambio: ${_dolar_det:,.0f} ARS/USD"
            if sin_costo_tn > 0:
                caption_txt += f" · ⚠️ {sin_costo_tn} orden(es) sin costo cargado"
            st.caption(caption_txt)

            st.dataframe(
                df_det[cols_tn].style
                    .format({
                        "Total ($)": "${:,.0f}", "Descuento ($)": "${:,.0f}",
                        "Envio costo ($)": "${:,.0f}", "Comision PN ($)": "${:,.0f}",
                        "Costo PN (%)": "{:.2f}%", "Neto cobrado ($)": "${:,.0f}",
                        "Costo Productos ($)": "${:,.0f}", "Margen ($)": "${:,.0f}",
                        "Margen (%)": "{:.2f}%",
                    })
                    .apply(_color_margen_row, axis=1),
                use_container_width=True, hide_index=True,
            )
            st.download_button("⬇️ Descargar CSV órdenes TN",
                df_det[cols_tn].to_csv(index=False).encode("utf-8"), "ordenes_tn.csv", "text/csv")

            # Métricas resumen
            st.divider()
            total_bruto = df_det["Total ($)"].sum()
            total_costo = df_det["Costo Productos ($)"].sum()
            total_comis = df_det["Comision PN ($)"].sum()
            total_margen = df_det["Margen ($)"].sum()
            mg1, mg2, mg3, mg4 = st.columns(4)
            mg1.metric("💰 Facturación bruta", fmt(total_bruto))
            mg2.metric("📦 Costo productos", fmt(total_costo), delta=f"-{fmt(total_costo)}", delta_color="inverse")
            mg3.metric("💳 Comisión PN", fmt(total_comis), delta=f"-{fmt(total_comis)}", delta_color="inverse")
            mg4.metric(
                f"{'🟢' if total_margen >= 0 else '🔴'} Margen neto",
                fmt(total_margen),
                delta=f"{round(total_margen / total_bruto * 100, 1)}% sobre bruto" if total_bruto > 0 else None,
            )

            # Estado de costos
            st.divider()
            st.subheader("📋 Estado de costos por producto")
            todos_prods = set()
            for _, row in df_tn.iterrows():
                for p in str(row.get("Productos", "")).split(" / "):
                    p = p.strip()
                    if p:
                        todos_prods.add(p)

            filas_estado = []
            for p in sorted(todos_prods):
                fob = get_fob_usd(p, _costos_gs)
                filas_estado.append({
                    "Estado": "✅" if fob > 0 else "❌",
                    "Producto (nombre en TN)": p,
                    "FOB (USD)": fob if fob > 0 else None,
                    "Costo ARS": round(fob * _dolar_det) if fob > 0 else None,
                })
            df_estado = pd.DataFrame(filas_estado)
            sin_costo_n = len(df_estado[df_estado["Estado"] == "❌"])
            cc1, cc2 = st.columns(2)
            cc1.metric("✅ Con costo", len(df_estado) - sin_costo_n)
            cc2.metric("❌ Sin costo", sin_costo_n)
            if sin_costo_n > 0:
                st.info("💡 Cargá los costos faltantes en la solapa **💻 Costos de consolas**.")
            st.dataframe(
                df_estado.style.map(
                    lambda v: "background-color: #1a3a1a" if v == "✅" else ("background-color: #3a1a1a" if v == "❌" else ""),
                    subset=["Estado"],
                ).format({"FOB (USD)": lambda x: f"${x:.2f}" if x else "—", "Costo ARS": lambda x: f"${x:,.0f}" if x else "—"}),
                use_container_width=True, hide_index=True,
            )

        # Resumen por medio de pago
        st.divider()
        st.subheader("📊 Resumen por medio de pago")
        if not df_tn.empty:
            res = df_tn.groupby("Medio de Pago").agg(
                Cantidad=("Orden", "count"), Bruto=("Total ($)", "sum"),
                Comision=("Comision PN ($)", "sum"), Neto=("Neto cobrado ($)", "sum"),
                CostoProds=("Costo Productos ($)", "sum"), Margen=("Margen ($)", "sum"),
            ).reset_index()
            res["Costo %"] = (res["Comision"] / res["Bruto"] * 100).round(2).apply(fmt_pct)
            res["Margen %"] = (res["Margen"] / res["Bruto"] * 100).round(2).apply(fmt_pct)
            for col in ["Bruto", "Comision", "Neto", "CostoProds", "Margen"]:
                res[col] = res[col].apply(fmt)
            res.columns = ["Medio de Pago", "Cantidad", "Bruto ($)", "Comision PN ($)", "Neto ($)", "Costo Prods ($)", "Margen ($)", "Costo PN %", "Margen %"]
            st.dataframe(res, use_container_width=True, hide_index=True)

        if not df_pagos.empty:
            st.divider()
            st.subheader("💳 Detalle transacciones — Pago Nube")
            st.dataframe(
                df_pagos.style.format({"Monto ($)": "${:,.0f}", "Fee ($)": "${:,.0f}", "Neto ($)": "${:,.0f}"}),
                use_container_width=True, hide_index=True,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3: SALUD FINANCIERA
    # ══════════════════════════════════════════════════════════════════════════
    with tab3:
        st.subheader("💚 Salud Financiera del Período")

        # ── Configuración con form para evitar rerun al cambiar valores ──
        with st.expander("⚙️ Configuración", expanded=True):
            with st.form("config_salud_financiera"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    dolar_default = int(dolar_blue) if dolar_blue else 1200
                    tipo_cambio = st.number_input(
                        f"💵 Dólar blue (auto: ${dolar_default:,.0f})" if dolar_blue else "💵 Tipo de cambio",
                        value=st.session_state.tipo_cambio_sf or dolar_default, step=10,
                    )
                with col2:
                    pct_iva = st.slider("🧾 IVA efectivo (%)", 0.0, 21.0, st.session_state.pct_iva, 0.5)
                with col3:
                    pauta_manual = st.number_input("📣 Pauta publicitaria (ARS)", value=st.session_state.pauta_manual, step=50_000)
                submitted_config = st.form_submit_button("✅ Aplicar configuración", use_container_width=True)
                if submitted_config:
                    st.session_state.tipo_cambio_sf = tipo_cambio
                    st.session_state.pct_iva = pct_iva
                    st.session_state.pauta_manual = pauta_manual

        # Use stored values
        tipo_cambio = st.session_state.tipo_cambio_sf or (int(dolar_blue) if dolar_blue else 1200)
        pct_iva = st.session_state.pct_iva
        pauta_manual = st.session_state.pauta_manual

        # Tasas de Pago Nube
        tasas_reales = calcular_tasas_reales(df_pagos) if not df_pagos.empty else None

        with st.expander("💳 Tasas de Pago Nube por cuotas (ajustables)", expanded=False):
            st.caption(
                "📌 Estas tasas se usan para **recalcular la comisión de cada orden** en esta solapa. "
                "Ajustalas si tus tasas reales difieren de las teóricas de PN."
            )
            if tasas_reales:
                st.success(f"✅ Tasas calculadas desde {len(df_pagos)} transacciones reales de Pago Nube")
                st.json(tasas_reales)
            else:
                st.info("Tasas calibradas manualmente. Si Pago Nube envía datos de fees, se auto-calculan.")

            tc1, tc2, tc3, tc4, tc5, tc6 = st.columns(6)
            tasa_1c  = tc1.number_input("1 cuota (%)",  value=4.15,  step=0.01, key="t1") / 100
            tasa_2c  = tc2.number_input("2 cuotas (%)", value=11.78, step=0.01, key="t2") / 100
            tasa_3c  = tc3.number_input("3 cuotas (%)", value=14.20, step=0.01, key="t3") / 100
            tasa_6c  = tc4.number_input("6 cuotas (%)", value=23.70, step=0.01, key="t6") / 100
            tasa_12c = tc5.number_input("12 cuotas (%)", value=43.24, step=0.01, key="t12") / 100
            tasa_deb = tc6.number_input("Deb/Trans (%)", value=4.15,  step=0.01, key="tdeb") / 100
            tasas_custom = {
                1: tasa_1c, 2: tasa_2c, 3: tasa_3c, 6: tasa_6c,
                9: (tasa_6c + tasa_12c) / 2, 12: tasa_12c,
                18: tasa_12c * 1.15, 24: tasa_12c * 1.30, "debit": tasa_deb,
            }

        st.divider()
        st.subheader("💰 Resumen financiero del período")

        if df_tn.empty:
            st.info("Buscá primero para ver los datos financieros.")
        else:
            def comision_custom(row):
                metodo = str(row.get("Medio de Pago", "")).lower()
                cuotas = int(row.get("Cuotas", 1) or 1)
                total = float(row.get("Total ($)", 0))
                if "debit" in metodo or "debito" in metodo or "transfer" in metodo or "dinero" in metodo:
                    tasa = tasas_custom.get("debit", 0.0199)
                else:
                    opciones = [k for k in tasas_custom if isinstance(k, int)]
                    tasa_key = min(opciones, key=lambda x: abs(x - cuotas))
                    tasa = tasas_custom.get(tasa_key, 0.0414)
                return round(total * tasa, 2)

            _costos_gs_sf = gs_read("CostosConsolas") or {}
            df_calc = df_tn.copy()
            df_calc["Comision PN ($)"] = df_calc.apply(comision_custom, axis=1)
            df_calc["Neto cobrado ($)"] = df_calc["Total ($)"] - df_calc["Comision PN ($)"]
            df_calc["Costo Productos ($)"] = df_calc.apply(
                lambda r: costo_final_row(r, tipo_cambio, _costos_gs_sf), axis=1
            )
            df_calc["Margen ($)"] = (
                df_calc["Neto cobrado ($)"] - df_calc["Costo Productos ($)"] - df_calc["Envio costo ($)"]
            )

            facturacion_bruta = df_calc["Total ($)"].sum()
            comisiones_pn = df_calc["Comision PN ($)"].sum()
            neto_cobrado = df_calc["Neto cobrado ($)"].sum()
            costo_productos = df_calc["Costo Productos ($)"].sum()
            costo_envios = df_calc["Envio costo ($)"].sum()
            costo_iva = facturacion_bruta * (pct_iva / 100)
            margen_bruto = df_calc["Margen ($)"].sum()

            # ── Gastos fijos prorrateados ──
            gastos_fijos_saved = gs_read("GastosFijos") or {}
            total_gastos_fijos_mes = sum(
                v for k, v in gastos_fijos_saved.items()
                if isinstance(v, (int, float)) and v > 0
            )
            dias_periodo = max((fecha_hasta - fecha_desde).days + 1, 1)
            factor_prorrateo = dias_periodo / 30
            gastos_fijos_periodo = round(total_gastos_fijos_mes * factor_prorrateo)

            resultado_final = margen_bruto - costo_iva - pauta_manual - gastos_fijos_periodo

            # Métricas principales
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Facturación bruta", fmt(facturacion_bruta))
            k2.metric("Comisiones PN", fmt(comisiones_pn), delta=f"-{fmt(comisiones_pn)}", delta_color="inverse")
            k3.metric("Neto cobrado", fmt(neto_cobrado))
            k4.metric("Costo productos", fmt(costo_productos), delta=f"-{fmt(costo_productos)}", delta_color="inverse")
            k5.metric("Costo envíos", fmt(costo_envios), delta=f"-{fmt(costo_envios)}", delta_color="inverse")

            st.divider()
            g1, g2, g3, g4 = st.columns(4)
            g1.metric("Margen bruto", fmt(margen_bruto))
            g2.metric(f"IVA ({pct_iva:.1f}%)", fmt(costo_iva), delta=f"-{fmt(costo_iva)}", delta_color="inverse")
            g3.metric("Pauta publicitaria", fmt(pauta_manual), delta=f"-{fmt(pauta_manual)}", delta_color="inverse")
            g4.metric(
                f"Gastos fijos ({dias_periodo}d)",
                fmt(gastos_fijos_periodo),
                delta=f"-{fmt(gastos_fijos_periodo)}",
                delta_color="inverse",
                help=f"${total_gastos_fijos_mes:,.0f}/mes × {factor_prorrateo:.2f} = ${gastos_fijos_periodo:,.0f}",
            )

            st.divider()
            st.metric(
                f"{'🟢' if resultado_final >= 0 else '🔴'} RESULTADO FINAL DEL PERÍODO",
                fmt(resultado_final),
            )
            if resultado_final >= 0:
                st.success(f"✅ Resultado positivo: {fmt(resultado_final)}")
            else:
                st.error(f"⚠️ Resultado negativo: -{fmt(abs(resultado_final))}")

            # ── Gráfico de resultado día a día ──
            st.divider()
            st.subheader("📈 Resultado diario — Tendencia del período")

            # Calcular P&L por día
            df_daily = df_calc.groupby("Fecha").agg(
                Facturacion=("Total ($)", "sum"),
                Comision=("Comision PN ($)", "sum"),
                Costo_Prods=("Costo Productos ($)", "sum"),
                Costo_Envio=("Envio costo ($)", "sum"),
            ).reset_index()

            # Prorratear gastos diarios
            iva_diario = df_daily["Facturacion"] * (pct_iva / 100)
            pauta_diaria = pauta_manual / dias_periodo
            gastos_fijos_diario = gastos_fijos_periodo / dias_periodo

            df_daily["Margen_Bruto"] = (
                df_daily["Facturacion"] - df_daily["Comision"] - df_daily["Costo_Prods"] - df_daily["Costo_Envio"]
            )
            df_daily["Resultado"] = (
                df_daily["Margen_Bruto"] - iva_diario - pauta_diaria - gastos_fijos_diario
            ).round(0)
            df_daily["Resultado_Acum"] = df_daily["Resultado"].cumsum()

            # Colores por resultado positivo/negativo
            df_daily["Color"] = df_daily["Resultado"].apply(lambda x: "#00C49F" if x >= 0 else "#FF5733")

            fig_daily = go.Figure()

            # Barras de resultado diario
            fig_daily.add_trace(go.Bar(
                x=df_daily["Fecha"], y=df_daily["Resultado"],
                name="Resultado diario",
                marker_color=df_daily["Color"],
                text=df_daily["Resultado"].apply(lambda x: f"${x:,.0f}"),
                textposition="outside",
                textfont_size=10,
            ))

            # Línea acumulada
            fig_daily.add_trace(go.Scatter(
                x=df_daily["Fecha"], y=df_daily["Resultado_Acum"],
                name="Acumulado",
                mode="lines+markers",
                line=dict(color="#009EE3", width=3),
                marker=dict(size=7),
                yaxis="y2",
            ))

            fig_daily.update_layout(
                title="Resultado neto por día + acumulado",
                yaxis=dict(title="Resultado diario ($)", tickformat="$,.0f"),
                yaxis2=dict(title="Acumulado ($)", overlaying="y", side="right", tickformat="$,.0f", showgrid=False),
                legend=dict(orientation="h", y=-0.15),
                hovermode="x unified",
            )
            st.plotly_chart(fig_daily, use_container_width=True)

            # Indicador de tendencia
            if len(df_daily) >= 3:
                ultimos_3 = df_daily["Resultado"].tail(3).mean()
                primeros_3 = df_daily["Resultado"].head(3).mean()
                if ultimos_3 > primeros_3 * 1.1:
                    st.success("📈 Tendencia alcista: los últimos días vienen mejor que el arranque del período.")
                elif ultimos_3 < primeros_3 * 0.9:
                    st.warning("📉 Tendencia bajista: los últimos días vienen más flojos que el arranque.")
                else:
                    st.info("➡️ Tendencia estable durante el período.")

            # Detalle por orden
            st.divider()
            st.subheader("📋 Detalle por orden con margen real")
            cols_fin = [
                "Orden", "Fecha", "Cliente", "Medio de Pago", "Cuotas", "Total ($)",
                "Comision PN ($)", "Neto cobrado ($)", "Costo Productos ($)",
                "Envio costo ($)", "Margen ($)", "Margen (%)",
            ]
            cols_fin = [c for c in cols_fin if c in df_calc.columns]
            st.dataframe(
                df_calc[cols_fin].style.format({
                    "Total ($)": "${:,.0f}", "Comision PN ($)": "${:,.0f}",
                    "Neto cobrado ($)": "${:,.0f}", "Costo Productos ($)": "${:,.0f}",
                    "Envio costo ($)": "${:,.0f}", "Margen ($)": "${:,.0f}", "Margen (%)": "{:.1f}%",
                }),
                use_container_width=True, hide_index=True,
            )

            # Cascada
            st.divider()
            st.subheader("📊 Cascada de resultados")
            wf = pd.DataFrame({
                "Concepto": [
                    "Facturación bruta", "Comisiones PN", "Costo productos",
                    "Costo envíos", f"IVA ({pct_iva:.1f}%)", "Pauta",
                    "Gastos fijos", "Resultado final",
                ],
                "Monto": [
                    facturacion_bruta, -comisiones_pn, -costo_productos,
                    -costo_envios, -costo_iva, -pauta_manual,
                    -gastos_fijos_periodo, resultado_final,
                ],
                "Color": [
                    "#00C49F", "#FF9900", "#FF5733", "#FF5733", "#FF5733",
                    "#FF9900", "#FF9900",
                    "#009EE3" if resultado_final >= 0 else "#FF0000",
                ],
            })
            fig_wf = px.bar(wf, x="Concepto", y="Monto", color="Concepto",
                color_discrete_sequence=wf["Color"].tolist(), title="Cascada financiera")
            fig_wf.update_layout(showlegend=False, yaxis_tickformat="$,.0f")
            fig_wf.update_traces(texttemplate="%{y:$,.0f}", textposition="outside")
            st.plotly_chart(fig_wf, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4: STOCK
    # ══════════════════════════════════════════════════════════════════════════
    with tab4:
        st.subheader("📦 Stock — Tienda Nube")

        @st.fragment
        def cargar_stock():
            if st.button("🔄 Cargar stock desde Tienda Nube", use_container_width=False):
                with st.spinner("Consultando productos y stock..."):
                    productos = get_tn_products()
                if productos:
                    stock_rows = []
                    for p in productos:
                        nombre_raw = p.get("name", {})
                        nombre = nombre_raw.get("es", "") if isinstance(nombre_raw, dict) else str(nombre_raw)
                        for v in p.get("variants", []):
                            stock = v.get("stock", None)
                            vals = v.get("values", [])
                            variante = " / ".join([
                                (val.get("es", "") or next(iter(val.values()), ""))
                                if isinstance(val, dict) else str(val)
                                for val in vals
                            ]) if vals else "—"
                            stock_rows.append({
                                "Producto": nombre,
                                "Variante": variante,
                                "SKU": v.get("sku", ""),
                                "Stock": stock if stock is not None else "Sin límite",
                                "Precio ($)": float(v.get("price", 0) or 0),
                            })
                    st.session_state.stock_tn = pd.DataFrame(stock_rows)
                    st.success(f"✅ {len(stock_rows)} variantes cargadas")
                else:
                    st.warning("No se pudieron cargar productos.")

            if "stock_tn" in st.session_state and st.session_state.stock_tn is not None:
                df_stock = st.session_state.stock_tn
                col_f1, col_f2 = st.columns(2)
                buscar_prod = col_f1.text_input("🔍 Buscar producto", "")
                mostrar_sin_stock = col_f2.checkbox("Solo sin stock o bajo", value=False)

                df_stock_f = df_stock.copy()
                if buscar_prod:
                    df_stock_f = df_stock_f[df_stock_f["Producto"].str.contains(buscar_prod, case=False, na=False)]
                if mostrar_sin_stock:
                    df_stock_f = df_stock_f[df_stock_f["Stock"].apply(lambda x: isinstance(x, (int, float)) and x <= 3)]

                st.dataframe(
                    df_stock_f.style.format({"Precio ($)": "${:,.0f}"}),
                    use_container_width=True, hide_index=True,
                )

                st.divider()
                st.subheader("⚠️ Alertas de stock bajo")
                umbral = st.slider("Umbral (unidades)", 1, 20, 5)
                alertas = df_stock[df_stock["Stock"].apply(lambda x: isinstance(x, (int, float)) and x <= umbral)]
                if alertas.empty:
                    st.success(f"✅ Todos con más de {umbral} unidades.")
                else:
                    st.warning(f"⚠️ {len(alertas)} variante(s) con stock ≤ {umbral}")
                    st.dataframe(alertas.style.format({"Precio ($)": "${:,.0f}"}),
                        use_container_width=True, hide_index=True)

                st.divider()
                stock_num = df_stock[df_stock["Stock"].apply(lambda x: isinstance(x, (int, float)))]
                r1, r2, r3 = st.columns(3)
                r1.metric("Total productos", df_stock["Producto"].nunique())
                r2.metric("Total variantes", len(df_stock))
                r3.metric("Total unidades", int(stock_num["Stock"].sum()))
                st.download_button("⬇️ Descargar stock",
                    df_stock.to_csv(index=False).encode("utf-8"), "stock_marketgamer.csv", "text/csv")
            else:
                st.info("👆 Hacé clic en 'Cargar stock' para ver el inventario.")

        cargar_stock()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 5: VELOCIDAD DE VENTAS
    # ══════════════════════════════════════════════════════════════════════════
    with tab5:
        st.subheader("🔥 Velocidad de ventas y planificación de restock")
        if df_tn.empty:
            st.info("Buscá primero para ver los datos.")
        else:
            dias_periodo = max((fecha_hasta - fecha_desde).days + 1, 1)
            ventas_por_prod = {}
            for _, row in df_tn.iterrows():
                prods_list = [p.strip() for p in str(row.get("Productos", "")).split(" / ") if p.strip()]
                n_prods = max(len(prods_list), 1)
                for p in prods_list:
                    if p not in ventas_por_prod:
                        ventas_por_prod[p] = {"unidades": 0, "revenue": 0.0, "ordenes": 0}
                    ventas_por_prod[p]["unidades"] += int(row.get("Cantidad", 1) or 1)
                    ventas_por_prod[p]["revenue"] += row.get("Total ($)", 0) / n_prods
                    ventas_por_prod[p]["ordenes"] += 1

            if not ventas_por_prod:
                st.info("No hay datos de productos.")
            else:
                stock_map = {}
                if "stock_tn" in st.session_state and st.session_state.stock_tn is not None:
                    for _, srow in st.session_state.stock_tn.iterrows():
                        pn = srow["Producto"]
                        sv = srow["Stock"]
                        if isinstance(sv, (int, float)):
                            stock_map[pn] = stock_map.get(pn, 0) + int(sv)

                with st.expander("⚙️ Configuración de alertas", expanded=False):
                    ca, cb = st.columns(2)
                    dias_alerta = ca.slider("⚠️ Alertar si queda stock para menos de X días", 1, 60, 14)
                    dias_restock = cb.slider("📦 Lead time restock (días)", 1, 45, 7)

                rows_vel = []
                for prod, data in ventas_por_prod.items():
                    vel_dia = round(data["unidades"] / dias_periodo, 3)
                    stock_actual = stock_map.get(prod)
                    dias_restantes = None
                    fecha_agot_str = "Sin stock cargado"
                    necesita_restock = False
                    restock_units = 0

                    if stock_actual is not None and vel_dia > 0:
                        dias_restantes = round(stock_actual / vel_dia, 0)
                        fecha_agot_str = (pd.Timestamp.now() + pd.Timedelta(days=dias_restantes)).strftime("%d/%m/%Y")
                        necesita_restock = dias_restantes <= (dias_alerta + dias_restock)
                        restock_units = max(0, round(vel_dia * 30 - stock_actual + vel_dia * dias_restock))
                    elif stock_actual is not None:
                        fecha_agot_str = "—"

                    urgencia = 0
                    if dias_restantes is not None and vel_dia > 0:
                        urgencia = min(100, round((vel_dia * 10) + max(0, (30 - dias_restantes) * 2)))
                    else:
                        urgencia = round(vel_dia * 10)

                    rows_vel.append({
                        "Producto": prod,
                        "Unidades vendidas": data["unidades"],
                        "Vel. diaria": vel_dia,
                        "Vel. semanal": round(vel_dia * 7, 2),
                        "Vel. mensual": round(vel_dia * 30, 1),
                        "Revenue ($)": round(data["revenue"]),
                        "Stock actual": stock_actual if stock_actual is not None else "—",
                        "Días restantes": int(dias_restantes) if dias_restantes is not None else "—",
                        "Se agota": fecha_agot_str,
                        "Restock sugerido": restock_units if restock_units > 0 else "—",
                        "Urgencia": urgencia,
                        "_necesita_restock": necesita_restock,
                    })

                df_vel = pd.DataFrame(rows_vel).sort_values("Urgencia", ascending=False)
                criticos = df_vel[df_vel["_necesita_restock"]]

                v1, v2, v3, v4 = st.columns(4)
                v1.metric("Productos", len(df_vel))
                v2.metric("🔴 Críticos", len(criticos))
                v3.metric("Período", f"{dias_periodo} días")
                v4.metric("Vel. media", f"{df_vel['Vel. diaria'].mean():.2f} u/día")

                if not criticos.empty:
                    st.divider()
                    st.error(f"⚠️ {len(criticos)} producto(s) necesitan restock")
                    for _, crow in criticos.iterrows():
                        dr = crow["Días restantes"]
                        st.warning(
                            f"🔴 **{crow['Producto']}** — stock para **{dr} días** | "
                            f"vel. {crow['Vel. diaria']} u/día | restock: **{crow['Restock sugerido']} u**"
                        )

                st.divider()
                df_chart = df_vel[["Producto", "Vel. diaria"]].sort_values("Vel. diaria", ascending=True).tail(15)
                fig_vel = px.bar(df_chart, x="Vel. diaria", y="Producto", orientation="h",
                    title="Velocidad de venta (u/día)", color="Vel. diaria",
                    color_continuous_scale=["#00C49F", "#FFD700", "#FF5733"], text="Vel. diaria")
                fig_vel.update_layout(showlegend=False, coloraxis_showscale=False,
                    yaxis={"categoryorder": "total ascending"})
                fig_vel.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                st.plotly_chart(fig_vel, use_container_width=True)

                cols_show = [
                    "Producto", "Unidades vendidas", "Vel. diaria", "Vel. semanal",
                    "Vel. mensual", "Revenue ($)", "Stock actual", "Días restantes",
                    "Se agota", "Restock sugerido", "Urgencia",
                ]
                st.dataframe(
                    df_vel[cols_show].style
                        .format({"Revenue ($)": "${:,.0f}", "Vel. diaria": "{:.3f}", "Vel. semanal": "{:.1f}"})
                        .map(lambda v: (
                            "background-color: #5a1a1a; color: #ff6b6b" if isinstance(v, (int, float)) and v >= 70
                            else "background-color: #5a4a1a; color: #ffd700" if isinstance(v, (int, float)) and v >= 40
                            else "background-color: #1a3a1a; color: #00C49F" if isinstance(v, (int, float))
                            else ""
                        ), subset=["Urgencia"])
                        .map(lambda v: (
                            "background-color: #5a1a1a; color: #ff6b6b" if isinstance(v, (int, float)) and v <= 7
                            else "background-color: #5a4a1a; color: #ffd700" if isinstance(v, (int, float)) and v <= 14
                            else ""
                        ), subset=["Días restantes"]),
                    use_container_width=True, hide_index=True,
                )

                st.divider()
                st.subheader("📈 Evolución de ventas")
                prod_sel = st.selectbox("Producto", df_vel["Producto"].tolist())
                if prod_sel:
                    df_evo = df_tn[df_tn["Productos"].str.contains(prod_sel, na=False, regex=False)]
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
                    df_vel[cols_show].to_csv(index=False).encode("utf-8"), "restock_analysis.csv", "text/csv")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 6: GASTOS FIJOS
    # ══════════════════════════════════════════════════════════════════════════
    with tab6:
        st.subheader("🏗️ Gastos fijos mensuales")
        st.caption("Los datos quedan guardados en Google Sheets.")

        if "gastos_fijos" not in st.session_state:
            saved = gs_read("GastosFijos")
            st.session_state.gastos_fijos = saved if saved else {
                "Bruno": 0, "Coco": 0, "Agencia": 0, "Local": 0,
                "Sueldo Agus": 0, "Sueldo Stella": 0, "Contador": 0,
                "Sueldo Facu": 0, "Otros": 0,
            }

        gastos = st.session_state.gastos_fijos.copy()

        st.markdown("**Editá, agregá o eliminá gastos fijos (ARS):**")
        nuevos_gastos = {}
        gastos_a_eliminar = []
        items = list(gastos.items())

        for i, (k, v) in enumerate(items):
            col_name, col_val, col_del = st.columns([3, 2, 0.5])
            with col_name:
                st.markdown(f"**{k}**")
            with col_val:
                nuevos_gastos[k] = st.number_input(
                    f"monto_{k}", value=int(v), step=50_000,
                    key=f"gf_{k}", label_visibility="collapsed",
                )
            with col_del:
                if st.button("🗑️", key=f"del_{k}", help=f"Eliminar {k}"):
                    gastos_a_eliminar.append(k)

        if gastos_a_eliminar:
            for k in gastos_a_eliminar:
                nuevos_gastos.pop(k, None)
                st.session_state.gastos_fijos.pop(k, None)
            gs_write("GastosFijos", nuevos_gastos)
            st.session_state.gastos_fijos = nuevos_gastos
            st.rerun()

        st.divider()
        with st.expander("➕ Agregar gasto"):
            ng1, ng2, ng3 = st.columns([2, 2, 1])
            nuevo_nombre = ng1.text_input("Nombre")
            nuevo_monto = ng2.number_input("Monto mensual (ARS)", value=0, step=50_000, key="ng_monto")
            with ng3:
                st.write("")
                st.write("")
                if st.button("Agregar", type="primary"):
                    if nuevo_nombre and nuevo_nombre not in nuevos_gastos:
                        nuevos_gastos[nuevo_nombre] = nuevo_monto
                        st.session_state.gastos_fijos = nuevos_gastos
                        gs_write("GastosFijos", nuevos_gastos)
                        st.rerun()

        if st.button("💾 Guardar gastos fijos", use_container_width=True, type="primary"):
            st.session_state.gastos_fijos = nuevos_gastos
            ok = gs_write("GastosFijos", nuevos_gastos)
            st.success("✅ Guardado en Google Sheets" if ok else "⚠️ Solo en sesión")

        st.divider()
        total_gastos = sum(v for v in nuevos_gastos.values() if isinstance(v, (int, float)))
        st.metric("💰 Total gastos fijos mensuales", fmt(total_gastos))

        df_gastos = pd.DataFrame(
            [(k, v) for k, v in nuevos_gastos.items() if isinstance(v, (int, float)) and v > 0],
            columns=["Concepto", "Monto (ARS)"],
        ).sort_values("Monto (ARS)", ascending=False)

        if not df_gastos.empty:
            fig_g = px.pie(df_gastos, names="Concepto", values="Monto (ARS)", hole=0.4,
                title="Distribución de gastos fijos", color_discrete_sequence=COLORES)
            st.plotly_chart(fig_g, use_container_width=True)

        if st.session_state.df_tn is not None and not st.session_state.df_tn.empty:
            st.divider()
            dias_p = max((fecha_hasta - fecha_desde).days + 1, 1)
            factor = dias_p / 30
            st.metric(f"📐 Gastos para {dias_p} días ({factor:.2f}x mes)", fmt(round(total_gastos * factor)))

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 7: COSTOS DE CONSOLAS
    # ══════════════════════════════════════════════════════════════════════════
    with tab7:
        st.subheader("💻 Costos de consolas")
        st.caption("FOB + importación. Los productos de TN se agregan sin sobreescribir datos existentes.")

        if "costos_consolas" not in st.session_state:
            saved = gs_read("CostosConsolas")
            st.session_state.costos_consolas = saved if saved else FOB_DEFAULTS.copy()

        tc_consolas = int(dolar_blue) if dolar_blue else 1200

        @st.fragment
        def cargar_productos_tn():
            if st.button("🔄 Actualizar productos desde Tienda Nube", key="btn_load_consolas"):
                with st.spinner("Cargando..."):
                    productos_tn = get_tn_products()
                if productos_tn:
                    prods_map = {}
                    for p in productos_tn:
                        nombre_raw = p.get("name", {})
                        nombre = nombre_raw.get("es", "") if isinstance(nombre_raw, dict) else str(nombre_raw)
                        peso_kg = None
                        for v in p.get("variants", []):
                            w = v.get("weight")
                            if w:
                                try:
                                    peso_kg = float(w)
                                    break
                                except Exception:
                                    pass
                        if not peso_kg:
                            try:
                                peso_kg = float(p.get("weight")) if p.get("weight") else None
                            except Exception:
                                peso_kg = None
                        prods_map[nombre] = peso_kg
                    st.session_state.productos_tn_map = prods_map

                    costos_actual = st.session_state.costos_consolas.copy()
                    nuevos = 0
                    for nombre, peso in prods_map.items():
                        if nombre not in costos_actual:
                            fob_def = FOB_DEFAULTS.get(nombre, {}).get("fob_usd", 0.0)
                            peso_def = peso or FOB_DEFAULTS.get(nombre, {}).get("peso_kg", 0.0)
                            costos_actual[nombre] = {
                                "fob_usd": fob_def,
                                "peso_kg": peso_def,
                            }
                            nuevos += 1
                        else:
                            existing = costos_actual[nombre]
                            if isinstance(existing, dict) and peso:
                                if not existing.get("peso_kg"):
                                    existing["peso_kg"] = peso
                    st.session_state.costos_consolas = costos_actual
                    st.success(f"✅ {len(prods_map)} productos cargados ({nuevos} nuevos agregados, existentes conservados)")
                else:
                    st.warning("No se pudieron cargar productos.")

        cargar_productos_tn()

        costos = st.session_state.costos_consolas.copy()
        productos_map = st.session_state.get("productos_tn_map", {})

        st.divider()
        col_imp1, col_imp2 = st.columns(2)
        costo_kg_usd = col_imp1.number_input(
            "📦 Costo importación (USD/kg)",
            value=float(costos.get("_costo_kg_usd", 65.0)), step=0.5, key="ckg",
        )
        col_imp2.metric("Dólar blue", f"${tc_consolas:,.0f} ARS")
        costos["_costo_kg_usd"] = costo_kg_usd

        st.divider()

        all_prods = set(productos_map.keys())
        for k in costos:
            if not k.startswith("_"):
                all_prods.add(k)

        if not all_prods:
            st.info("Cargá productos desde TN con el botón de arriba.")
        else:
            rows_costos = []
            for prod in sorted(all_prods):
                prod_data = costos.get(prod, {})
                if isinstance(prod_data, dict):
                    fob_saved = float(prod_data.get("fob_usd", 0.0) or 0.0)
                    peso_saved = float(prod_data.get("peso_kg", 0.0) or 0.0)
                else:
                    fob_saved = 0.0
                    peso_saved = 0.0

                peso_tn = productos_map.get(prod)
                peso_default_fob = FOB_DEFAULTS.get(prod, {}).get("peso_kg", 0.0)
                peso_final = float(peso_tn or peso_saved or peso_default_fob)

                fob_default = FOB_DEFAULTS.get(prod, {}).get("fob_usd", 0.0)
                fob_valor = fob_saved if fob_saved > 0 else float(fob_default)

                costo_import = round(peso_final * costo_kg_usd, 2)
                costo_total_usd = round(fob_valor + costo_import, 2)
                costo_total_ars = round(costo_total_usd * tc_consolas)

                rows_costos.append({
                    "Producto": prod,
                    "Peso (kg)": peso_final,
                    "FOB (USD)": fob_valor,
                    "Import (USD)": costo_import,
                    "Total (USD)": costo_total_usd,
                    "Total (ARS)": costo_total_ars,
                })

            df_costos_edit = pd.DataFrame(rows_costos)

            orden_col = st.selectbox(
                "Ordenar por", df_costos_edit.columns.tolist(),
                index=0, key="orden_costos",
            )
            orden_asc = st.checkbox("Ascendente", value=True, key="orden_asc")
            df_costos_edit = df_costos_edit.sort_values(orden_col, ascending=orden_asc)

            st.markdown("**Editá FOB y peso directamente:**")
            edited_df = st.data_editor(
                df_costos_edit,
                column_config={
                    "Producto": st.column_config.TextColumn("Producto", disabled=True),
                    "Peso (kg)": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, step=0.01, format="%.3f"),
                    "FOB (USD)": st.column_config.NumberColumn("FOB (USD)", min_value=0.0, step=0.5, format="$%.2f"),
                    "Import (USD)": st.column_config.NumberColumn("Import (USD)", disabled=True, format="$%.2f"),
                    "Total (USD)": st.column_config.NumberColumn("Total (USD)", disabled=True, format="$%.2f"),
                    "Total (ARS)": st.column_config.NumberColumn("Total (ARS)", disabled=True, format="$%d"),
                },
                hide_index=True,
                use_container_width=True,
                key="costos_editor",
            )

            if edited_df is not None:
                edited_df["Import (USD)"] = (edited_df["Peso (kg)"] * costo_kg_usd).round(2)
                edited_df["Total (USD)"] = (edited_df["FOB (USD)"] + edited_df["Import (USD)"]).round(2)
                edited_df["Total (ARS)"] = (edited_df["Total (USD)"] * tc_consolas).round(0).astype(int)

            st.divider()
            if st.button("💾 Guardar costos de consolas", use_container_width=True, type="primary"):
                nuevos_costos = {"_costo_kg_usd": costo_kg_usd}
                for _, row in edited_df.iterrows():
                    nuevos_costos[row["Producto"]] = {
                        "fob_usd": float(row["FOB (USD)"]),
                        "peso_kg": float(row["Peso (kg)"]),
                        "costo_import_usd": float(row["Import (USD)"]),
                        "costo_total_usd": float(row["Total (USD)"]),
                    }
                st.session_state.costos_consolas = nuevos_costos
                ok = gs_write("CostosConsolas", nuevos_costos)
                st.success("✅ Guardado en Google Sheets" if ok else "⚠️ Solo en sesión")

            st.divider()
            st.subheader("📊 Resumen de costos")
            st.dataframe(
                edited_df.style.format({
                    "FOB (USD)": "${:,.2f}", "Import (USD)": "${:,.2f}",
                    "Total (USD)": "${:,.2f}", "Total (ARS)": "${:,.0f}", "Peso (kg)": "{:.3f}",
                }),
                use_container_width=True, hide_index=True,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER: Extraer precios individuales por producto desde órdenes raw
    # ══════════════════════════════════════════════════════════════════════════
    def _build_product_rows_from_raw(orders_raw):
        """
        Extrae precio individual de cada producto desde la API de TN.
        Cada producto en la orden tiene su propio 'price', así que no
        dividimos el total de la orden entre productos.
        """
        product_rows = []
        for o in orders_raw:
            pd_raw = o.get("payment_details", {})
            gateway = str(o.get("gateway", "")).lower()
            metodo = gateway
            cuotas = 1
            if isinstance(pd_raw, dict):
                metodo = pd_raw.get("method", gateway)
                cuotas = int(pd_raw.get("installments", 1) or 1)

            if metodo == "credit_card":
                label_medio = "Credito contado" if cuotas == 1 else f"Credito {cuotas} cuotas"
            elif metodo == "debit_card":
                label_medio = "Debito"
            elif any(x in str(metodo).lower() for x in ["transfer", "wire"]):
                label_medio = "Transferencia"
            elif "account_money" in str(metodo).lower():
                label_medio = "Dinero en cuenta"
            else:
                label_medio = str(metodo).replace("_", " ").title() if metodo else str(gateway)

            try:
                fecha = pd.to_datetime(o.get("created_at", "")).strftime("%Y-%m-%d")
            except Exception:
                fecha = ""

            order_total = float(o.get("total", 0))
            n_products = len(o.get("products", []))
            costo_envio = float(o.get("shipping_cost_owner", 0) or 0)
            tasa = tasa_pago_nube(metodo, cuotas)

            for p in o.get("products", []):
                nombre = _extraer_nombre_producto(p.get("name", ""))
                precio_unit = float(p.get("price", 0) or 0)
                qty = int(p.get("quantity", 1) or 1)

                # Si el precio individual es 0, fallback a dividir total
                if precio_unit <= 0 and n_products > 0:
                    precio_unit = order_total / n_products

                # Comisión proporcional al precio del producto respecto al total
                if order_total > 0:
                    peso_en_orden = (precio_unit * qty) / order_total
                else:
                    peso_en_orden = 1.0 / max(n_products, 1)
                comision_unit = round(order_total * tasa * peso_en_orden / qty, 2)
                envio_unit = round(costo_envio * peso_en_orden / qty, 2)

                for _ in range(qty):
                    product_rows.append({
                        "Producto": nombre,
                        "Precio ($)": round(precio_unit, 0),
                        "Medio de Pago": label_medio,
                        "Cuotas": cuotas,
                        "Comisión PN ($)": round(comision_unit, 0),
                        "Tasa PN (%)": round(tasa * 100, 2),
                        "Envío ($)": round(envio_unit, 0),
                        "Fecha": fecha,
                        "Orden Total ($)": order_total,
                    })
        return product_rows

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 8: MARGEN TEÓRICO POR CONSOLA
    # ══════════════════════════════════════════════════════════════════════════
    with tab8:
        st.subheader("📐 Margen teórico por consola")
        st.caption(
            "Margen estimado usando el **precio individual** de cada producto (no el total de la orden), "
            "costo total (FOB + import + packaging + IVA), comisión PN y envío. "
            "Incluye tabla de rentabilidad por cantidad de cuotas."
        )

        _costos_gs_mt = gs_read("CostosConsolas") or {}
        _tc_mt = int(dolar_blue) if dolar_blue else 1200

        if df_tn.empty:
            st.info("Buscá primero para ver los datos.")
        else:
            orders_raw = st.session_state.orders_raw

            # ── Configuración de costos adicionales ──
            with st.expander("⚙️ Costos adicionales", expanded=True):
                cc1, cc2, cc3 = st.columns(3)
                with cc1:
                    iva_mt = cc1.number_input("🧾 IVA (%)", value=10.5, step=0.5, key="iva_mt")
                with cc2:
                    packaging_ars = cc2.number_input("📦 Packaging por unidad ($)", value=2500, step=500, key="pkg_mt")
                with cc3:
                    cc3.metric("Dólar blue", f"${_tc_mt:,.0f}")

            # ── Extraer precios individuales desde raw orders ──
            product_rows = _build_product_rows_from_raw(orders_raw)
            if not product_rows:
                st.info("No hay datos de productos.")
            else:
                df_prod_raw = pd.DataFrame(product_rows)

                # Precio promedio real por producto (precio individual, no total/n)
                precios_prod = df_prod_raw.groupby("Producto").agg(
                    Precio_prom=("Precio ($)", "mean"),
                    Unidades=("Precio ($)", "count"),
                ).reset_index()

                # Envío promedio del período
                envio_prom = df_tn["Envio costo ($)"].mean()

                # Tasa ponderada
                total_fact = df_tn["Total ($)"].sum()
                total_com = df_tn["Comision PN ($)"].sum()
                tasa_ponderada = total_com / total_fact if total_fact > 0 else 0.0415

                # ── Tabla principal de margen teórico ──
                rows_mt = []
                for _, prow in precios_prod.iterrows():
                    prod = prow["Producto"]
                    precio_prom = prow["Precio_prom"]
                    unidades = int(prow["Unidades"])

                    costo_total_usd = get_costo_total_usd(prod, _costos_gs_mt)
                    costo_total_ars = costo_total_usd * _tc_mt
                    costo_iva = round(precio_prom * (iva_mt / 100), 0)
                    costo_full = round(costo_total_ars + packaging_ars + costo_iva, 0)

                    comision_est = round(precio_prom * tasa_ponderada, 0)
                    margen_teorico = round(precio_prom - costo_full - comision_est - envio_prom, 0)
                    margen_pct = round(margen_teorico / precio_prom * 100, 1) if precio_prom > 0 else 0

                    rows_mt.append({
                        "Producto": prod,
                        "Precio prom ($)": round(precio_prom, 0),
                        "Costo prod ($)": round(costo_total_ars, 0),
                        "Packaging ($)": packaging_ars,
                        f"IVA ({iva_mt}%)": costo_iva,
                        "Costo full ($)": costo_full,
                        f"Comisión PN ({tasa_ponderada*100:.1f}%)": comision_est,
                        "Envío prom ($)": round(envio_prom, 0),
                        "Margen ($)": margen_teorico,
                        "Margen (%)": margen_pct,
                        "Uds": unidades,
                    })

                df_mt = pd.DataFrame(rows_mt).sort_values("Margen (%)", ascending=False)

                # Métricas
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Tasa PN ponderada", f"{tasa_ponderada*100:.2f}%")
                m2.metric("Envío promedio", fmt(envio_prom))
                m3.metric("Packaging/u", fmt(packaging_ars))
                m4.metric(f"IVA", f"{iva_mt}%")

                # Gráfico
                df_mt_chart = df_mt.sort_values("Margen (%)", ascending=True).tail(20)
                fig_mt = px.bar(
                    df_mt_chart, x="Margen (%)", y="Producto", orientation="h",
                    title="Margen teórico por consola (%)",
                    color="Margen (%)",
                    color_continuous_scale=["#FF5733", "#FFD700", "#00C49F"],
                    text="Margen (%)",
                )
                fig_mt.update_layout(
                    yaxis={"categoryorder": "total ascending"},
                    coloraxis_showscale=False,
                )
                fig_mt.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                st.plotly_chart(fig_mt, use_container_width=True)

                # Tabla principal
                st.divider()
                col_com_mt = f"Comisión PN ({tasa_ponderada*100:.1f}%)"
                col_iva_mt = f"IVA ({iva_mt}%)"
                st.dataframe(
                    df_mt.style
                        .format({
                            "Precio prom ($)": "${:,.0f}",
                            "Costo prod ($)": "${:,.0f}",
                            "Packaging ($)": "${:,.0f}",
                            col_iva_mt: "${:,.0f}",
                            "Costo full ($)": "${:,.0f}",
                            col_com_mt: "${:,.0f}",
                            "Envío prom ($)": "${:,.0f}",
                            "Margen ($)": "${:,.0f}",
                            "Margen (%)": "{:.1f}%",
                        })
                        .map(lambda v: (
                            "background-color: #1e4620; color: #00C49F" if isinstance(v, (int, float)) and v >= 20
                            else "background-color: #5a4a1a; color: #ffd700" if isinstance(v, (int, float)) and v >= 10
                            else "background-color: #4a1010; color: #ff6b6b" if isinstance(v, (int, float))
                            else ""
                        ), subset=["Margen (%)"]),
                    use_container_width=True, hide_index=True,
                )

                # ══════════════════════════════════════════════════════════════
                # TABLA DE RENTABILIDAD POR CUOTAS
                # ══════════════════════════════════════════════════════════════
                st.divider()
                st.subheader("💳 Rentabilidad por cantidad de cuotas")
                st.caption(
                    "Muestra cómo cambia el margen de cada consola según la cantidad de cuotas "
                    "que elija el cliente. La comisión de PN varía según el plan de cuotas."
                )

                # Tasas por cuota (usar las mismas que Salud Financiera si están cargadas)
                cuotas_config = {
                    "Débito/Trans": 0.0415,
                    "1 cuota": 0.0415,
                    "3 cuotas": 0.1420,
                    "6 cuotas": 0.2370,
                    "12 cuotas": 0.4324,
                }

                with st.expander("⚙️ Ajustar tasas por cuota", expanded=False):
                    tc_cols = st.columns(len(cuotas_config))
                    cuotas_ajustadas = {}
                    for i, (label, default) in enumerate(cuotas_config.items()):
                        with tc_cols[i]:
                            cuotas_ajustadas[label] = st.number_input(
                                f"{label} (%)", value=round(default * 100, 2),
                                step=0.1, key=f"cuota_mt_{label}",
                            ) / 100

                rows_cuotas = []
                for _, prow in precios_prod.iterrows():
                    prod = prow["Producto"]
                    precio = prow["Precio_prom"]

                    costo_total_usd = get_costo_total_usd(prod, _costos_gs_mt)
                    costo_total_ars = costo_total_usd * _tc_mt
                    costo_iva = round(precio * (iva_mt / 100), 0)
                    costo_full = round(costo_total_ars + packaging_ars + costo_iva, 0)

                    row_data = {
                        "Producto": prod,
                        "Precio ($)": round(precio, 0),
                        "Costo full ($)": costo_full,
                    }

                    for label, tasa in cuotas_ajustadas.items():
                        comision = round(precio * tasa, 0)
                        margen = round(precio - costo_full - comision - envio_prom, 0)
                        margen_pct = round(margen / precio * 100, 1) if precio > 0 else 0
                        row_data[f"M {label} ($)"] = margen
                        row_data[f"M {label} (%)"] = margen_pct

                    rows_cuotas.append(row_data)

                df_cuotas = pd.DataFrame(rows_cuotas).sort_values("Precio ($)", ascending=False)

                # Formato para las columnas de margen
                fmt_cuotas = {
                    "Precio ($)": "${:,.0f}",
                    "Costo full ($)": "${:,.0f}",
                }
                pct_cols = []
                for label in cuotas_ajustadas.keys():
                    fmt_cuotas[f"M {label} ($)"] = "${:,.0f}"
                    fmt_cuotas[f"M {label} (%)"] = "{:.1f}%"
                    pct_cols.append(f"M {label} (%)")

                def _color_margen_cuotas(v):
                    if isinstance(v, (int, float)):
                        if v >= 20:
                            return "background-color: #1e4620; color: #00C49F"
                        elif v >= 10:
                            return "background-color: #5a4a1a; color: #ffd700"
                        elif v >= 0:
                            return "background-color: #4a3a1a; color: #ffaa00"
                        else:
                            return "background-color: #4a1010; color: #ff6b6b"
                    return ""

                st.dataframe(
                    df_cuotas.style
                        .format(fmt_cuotas)
                        .map(_color_margen_cuotas, subset=pct_cols),
                    use_container_width=True, hide_index=True,
                )

                # Gráfico comparativo para un producto seleccionado
                st.divider()
                prod_sel_cuotas = st.selectbox(
                    "Ver detalle por cuotas de:",
                    df_cuotas["Producto"].tolist(),
                    key="sel_cuotas_mt",
                )
                if prod_sel_cuotas:
                    row_sel = df_cuotas[df_cuotas["Producto"] == prod_sel_cuotas].iloc[0]
                    chart_data = []
                    for label in cuotas_ajustadas.keys():
                        chart_data.append({
                            "Cuotas": label,
                            "Margen ($)": row_sel[f"M {label} ($)"],
                            "Margen (%)": row_sel[f"M {label} (%)"],
                            "Tasa PN (%)": round(cuotas_ajustadas[label] * 100, 2),
                        })
                    df_chart_cuotas = pd.DataFrame(chart_data)

                    fig_cuotas = go.Figure()
                    colors_cuotas = [
                        "#00C49F" if m >= 0 else "#FF5733"
                        for m in df_chart_cuotas["Margen ($)"]
                    ]
                    fig_cuotas.add_trace(go.Bar(
                        x=df_chart_cuotas["Cuotas"],
                        y=df_chart_cuotas["Margen ($)"],
                        name="Margen ($)",
                        marker_color=colors_cuotas,
                        text=df_chart_cuotas["Margen ($)"].apply(lambda x: f"${x:,.0f}"),
                        textposition="outside",
                    ))
                    fig_cuotas.add_trace(go.Scatter(
                        x=df_chart_cuotas["Cuotas"],
                        y=df_chart_cuotas["Margen (%)"],
                        name="Margen (%)",
                        mode="lines+markers+text",
                        line=dict(color="#009EE3", width=3),
                        marker=dict(size=10),
                        text=df_chart_cuotas["Margen (%)"].apply(lambda x: f"{x:.1f}%"),
                        textposition="top center",
                        yaxis="y2",
                    ))
                    fig_cuotas.update_layout(
                        title=f"Margen por cuotas — {prod_sel_cuotas} (Precio: {fmt(row_sel['Precio ($)'])})",
                        yaxis=dict(title="Margen ($)", tickformat="$,.0f"),
                        yaxis2=dict(title="Margen (%)", overlaying="y", side="right", ticksuffix="%", showgrid=False),
                        legend=dict(orientation="h", y=-0.15),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_cuotas, use_container_width=True)

                st.download_button("⬇️ Descargar margen teórico",
                    df_mt.to_csv(index=False).encode("utf-8"), "margen_teorico.csv", "text/csv")
                st.download_button("⬇️ Descargar rentabilidad por cuotas",
                    df_cuotas.to_csv(index=False).encode("utf-8"), "rentabilidad_cuotas.csv", "text/csv")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 9: MARGEN REAL POR CONSOLA
    # ══════════════════════════════════════════════════════════════════════════
    with tab9:
        st.subheader("📈 Margen real por consola y medio de pago")
        st.caption(
            "Margen real calculado orden por orden usando el **precio individual** de cada producto. "
            "Muestra cómo el medio de pago impacta en la rentabilidad."
        )

        if df_tn.empty:
            st.info("Buscá primero para ver los datos.")
        else:
            _costos_gs_mr = gs_read("CostosConsolas") or {}
            _tc_mr = int(dolar_blue) if dolar_blue else 1200
            orders_raw_mr = st.session_state.orders_raw

            # Config costos adicionales (compartido con tab 8)
            with st.expander("⚙️ Costos adicionales", expanded=True):
                cr1, cr2 = st.columns(2)
                iva_mr = cr1.number_input("🧾 IVA (%)", value=10.5, step=0.5, key="iva_mr")
                packaging_mr = cr2.number_input("📦 Packaging/u ($)", value=2500, step=500, key="pkg_mr")

            # Extraer precios individuales desde raw orders
            product_rows_mr = _build_product_rows_from_raw(orders_raw_mr)

            if not product_rows_mr:
                st.info("No hay datos de productos.")
            else:
                # Calcular margen real por cada línea de producto
                rows_real = []
                for pr in product_rows_mr:
                    prod = pr["Producto"]
                    precio = pr["Precio ($)"]
                    comision = pr["Comisión PN ($)"]
                    envio = pr["Envío ($)"]

                    costo_total_usd = get_costo_total_usd(prod, _costos_gs_mr)
                    costo_total_ars = costo_total_usd * _tc_mr
                    costo_iva = round(precio * (iva_mr / 100), 0)
                    costo_full = round(costo_total_ars + packaging_mr + costo_iva, 0)

                    neto = precio - comision
                    margen = round(neto - costo_full - envio, 0)

                    rows_real.append({
                        "Producto": prod,
                        "Medio de Pago": pr["Medio de Pago"],
                        "Cuotas": pr["Cuotas"],
                        "Precio ($)": round(precio, 0),
                        "Comisión PN ($)": round(comision, 0),
                        "Costo PN (%)": round(comision / precio * 100, 2) if precio > 0 else 0,
                        "Costo prod ($)": round(costo_total_ars, 0),
                        "Packaging ($)": packaging_mr,
                        f"IVA ({iva_mr}%)": costo_iva,
                        "Envío ($)": round(envio, 0),
                        "Margen ($)": margen,
                        "Margen (%)": round(margen / precio * 100, 1) if precio > 0 else 0,
                    })

                df_real = pd.DataFrame(rows_real)

                if df_real.empty:
                    st.info("No hay datos suficientes.")
                else:
                    # ── Vista 1: Margen promedio por producto ──
                    st.markdown("### Margen promedio real por consola")
                    col_iva_mr = f"IVA ({iva_mr}%)"
                    df_avg = df_real.groupby("Producto").agg(
                        Ventas=("Precio ($)", "count"),
                        Precio_prom=("Precio ($)", "mean"),
                        Comision_prom=("Comisión PN ($)", "mean"),
                        Costo_prom=("Costo prod ($)", "mean"),
                        Packaging_prom=("Packaging ($)", "mean"),
                        IVA_prom=(col_iva_mr, "mean"),
                        Envio_prom=("Envío ($)", "mean"),
                        Margen_prom=("Margen ($)", "mean"),
                        Margen_pct_prom=("Margen (%)", "mean"),
                    ).reset_index()
                    df_avg.columns = [
                        "Producto", "Ventas", "Precio prom ($)", "Comisión prom ($)",
                        "Costo prod ($)", "Packaging ($)", col_iva_mr, "Envío ($)",
                        "Margen prom ($)", "Margen (%)",
                    ]
                    df_avg = df_avg.sort_values("Margen (%)", ascending=False)

                    # Gráfico
                    df_avg_chart = df_avg.sort_values("Margen (%)", ascending=True).tail(20)
                    fig_mr = px.bar(
                        df_avg_chart, x="Margen (%)", y="Producto", orientation="h",
                        title="Margen real promedio por consola (%)",
                        color="Margen (%)",
                        color_continuous_scale=["#FF5733", "#FFD700", "#00C49F"],
                        text="Margen (%)",
                    )
                    fig_mr.update_layout(
                        yaxis={"categoryorder": "total ascending"},
                        coloraxis_showscale=False,
                    )
                    fig_mr.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                    st.plotly_chart(fig_mr, use_container_width=True)

                    st.dataframe(
                        df_avg.style.format({
                            "Precio prom ($)": "${:,.0f}",
                            "Comisión prom ($)": "${:,.0f}",
                            "Costo prod ($)": "${:,.0f}",
                            "Packaging ($)": "${:,.0f}",
                            col_iva_mr: "${:,.0f}",
                            "Envío ($)": "${:,.0f}",
                            "Margen prom ($)": "${:,.0f}",
                            "Margen (%)": "{:.1f}%",
                        }).map(lambda v: (
                            "background-color: #1e4620; color: #00C49F" if isinstance(v, (int, float)) and v >= 20
                            else "background-color: #5a4a1a; color: #ffd700" if isinstance(v, (int, float)) and v >= 10
                            else "background-color: #4a1010; color: #ff6b6b" if isinstance(v, (int, float))
                            else ""
                        ), subset=["Margen (%)"]),
                        use_container_width=True, hide_index=True,
                    )

                    # ── Vista 2: Impacto del medio de pago por consola ──
                    st.divider()
                    st.markdown("### Impacto del medio de pago en el margen")

                    prod_sel_mr = st.selectbox(
                        "Seleccioná un producto",
                        df_avg["Producto"].tolist(),
                        key="sel_margen_real",
                    )

                    if prod_sel_mr:
                        df_prod = df_real[df_real["Producto"] == prod_sel_mr]
                        df_by_medio = df_prod.groupby("Medio de Pago").agg(
                            Ventas=("Precio ($)", "count"),
                            Precio_prom=("Precio ($)", "mean"),
                            Comision_prom=("Comisión PN ($)", "mean"),
                            Costo_PN_pct=("Costo PN (%)", "mean"),
                            Margen_prom=("Margen ($)", "mean"),
                            Margen_pct=("Margen (%)", "mean"),
                        ).reset_index().sort_values("Margen_pct", ascending=False)
                        df_by_medio.columns = [
                            "Medio de Pago", "Ventas", "Precio prom ($)",
                            "Comisión prom ($)", "Costo PN (%)", "Margen prom ($)", "Margen (%)",
                        ]

                        col_mr1, col_mr2 = st.columns(2)
                        with col_mr1:
                            fig_medio = px.bar(
                                df_by_medio, x="Medio de Pago", y="Margen (%)",
                                title=f"Margen real por medio de pago — {prod_sel_mr}",
                                color="Margen (%)",
                                color_continuous_scale=["#FF5733", "#FFD700", "#00C49F"],
                                text="Margen (%)",
                            )
                            fig_medio.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                            fig_medio.update_layout(coloraxis_showscale=False)
                            st.plotly_chart(fig_medio, use_container_width=True)

                        with col_mr2:
                            fig_dist = px.pie(
                                df_by_medio, names="Medio de Pago", values="Ventas",
                                title=f"Distribución de ventas — {prod_sel_mr}",
                                color_discrete_sequence=COLORES, hole=0.35,
                            )
                            fig_dist.update_traces(textinfo="label+value+percent")
                            st.plotly_chart(fig_dist, use_container_width=True)

                        st.dataframe(
                            df_by_medio.style.format({
                                "Precio prom ($)": "${:,.0f}",
                                "Comisión prom ($)": "${:,.0f}",
                                "Costo PN (%)": "{:.2f}%",
                                "Margen prom ($)": "${:,.0f}",
                                "Margen (%)": "{:.1f}%",
                            }),
                            use_container_width=True, hide_index=True,
                        )

                        # Diferencia entre mejor y peor medio
                        if len(df_by_medio) >= 2:
                            mejor = df_by_medio.iloc[0]
                            peor = df_by_medio.iloc[-1]
                            diff = round(mejor["Margen (%)"] - peor["Margen (%)"], 1)
                            st.info(
                                f"💡 Diferencia de margen entre **{mejor['Medio de Pago']}** "
                                f"({mejor['Margen (%)']:.1f}%) y **{peor['Medio de Pago']}** "
                                f"({peor['Margen (%)']:.1f}%): **{diff} puntos porcentuales**"
                            )

                    st.divider()
                    st.download_button("⬇️ Descargar margen real detallado",
                        df_real.to_csv(index=False).encode("utf-8"), "margen_real_detallado.csv", "text/csv")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 10: PROVEEDORES
    # ══════════════════════════════════════════════════════════════════════════
    with tab10:
        st.markdown("""
        <style>
        /* ── Market Gamer · Proveedores ───────────────────────────────── */
        .prov-page-header{display:flex;align-items:baseline;gap:14px;padding-bottom:20px;border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:8px}
        .prov-page-title{font-size:22px;font-weight:700;color:#e2e8f0;letter-spacing:-.3px;margin:0}
        .prov-stat-pill{font-size:11px;font-weight:600;color:#6b7280;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);padding:3px 10px;border-radius:20px}
        .prov-section{font-size:10px;font-weight:700;color:#4b5563;letter-spacing:1.2px;text-transform:uppercase;padding:20px 0 10px;border-bottom:1px solid rgba(255,255,255,0.05);margin-bottom:14px}
        .sup-contact{font-size:12px;color:#6b7280;display:flex;gap:16px;margin-bottom:14px;flex-wrap:wrap}
        .sup-contact span{display:flex;align-items:center;gap:5px}
        .cat-tbl{width:100%;border-collapse:collapse;margin-bottom:16px}
        .cat-tbl th{font-size:10px;font-weight:700;color:#4b5563;text-transform:uppercase;letter-spacing:.7px;padding:6px 10px;border-bottom:1px solid rgba(255,255,255,0.07);text-align:left}
        .cat-tbl th.r{text-align:right}
        .cat-tbl td{font-size:13px;color:#94a3b8;padding:8px 10px;border-bottom:1px solid rgba(255,255,255,0.03)}
        .cat-tbl td.pn{color:#e2e8f0;font-weight:500}
        .cat-tbl td.pr{text-align:right;font-family:ui-monospace,monospace;font-size:14px;color:#cbd5e1;font-weight:600}
        .cat-tbl tr:hover td{background:rgba(255,255,255,0.02)}
        .brand-tag{display:inline-block;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;background:rgba(255,255,255,0.07);color:#94a3b8}
        .brand-anbernic{background:rgba(96,165,250,0.12);color:#60a5fa}
        .brand-powkiddy{background:rgba(251,191,36,0.12);color:#fbbf24}
        .brand-trimui{background:rgba(74,222,128,0.12);color:#4ade80}
        .brand-miyoo{background:rgba(192,132,252,0.12);color:#c084fc}
        .brand-retroid{background:rgba(251,146,60,0.12);color:#fb923c}
        .comp-banner{background:rgba(74,222,128,0.05);border:1px solid rgba(74,222,128,0.15);border-radius:8px;padding:14px 18px;margin:8px 0 16px;display:flex;align-items:center;gap:12px}
        .comp-banner-title{font-size:15px;font-weight:700;color:#e2e8f0}
        .comp-banner-sub{font-size:12px;color:#6b7280;margin-top:2px}
        </style>
        """, unsafe_allow_html=True)

        # ── Cargar datos guardados ──
        if "proveedores_data" not in st.session_state:
            saved_prov = gs_read("Proveedores")
            if saved_prov and "suppliers" in saved_prov:
                st.session_state.proveedores_data = saved_prov
            else:
                st.session_state.proveedores_data = {
                    "suppliers": {
                        "Anne - Qbuy Technology": {
                            "contacto": "Anne Lee | WhatsApp: +86 181 7167 5976 | Wechat: qbuy18",
                            "web": "qbuytech.en.alibaba.com",
                            "updated_at": "",
                            "productos": {
                                "R36S": {"precio_usd": 23.2, "storage": "64G", "marca": "R36 Series", "screen": "3.5in 640x480", "cpu": "RK3326", "battery": "3200mAh"},
                                "R36H": {"precio_usd": 27.5, "storage": "64G", "marca": "R36 Series", "screen": "3.5in 640x480", "cpu": "RK3326", "battery": "3000mAh"},
                                "R36S PLUS": {"precio_usd": 28.4, "storage": "64G", "marca": "R36 Series", "screen": "3.5in 640x480", "cpu": "RK3326", "battery": "3200mAh"},
                                "RG35XX PRO": {"precio_usd": 45.7, "storage": "64G", "marca": "Anbernic", "screen": "3.5in 640x480", "cpu": "H700", "battery": "3300mAh"},
                                "RG406V": {"precio_usd": 161.7, "storage": "128G", "marca": "Anbernic", "screen": "4in 960x720", "cpu": "T820", "battery": "5500mAh"},
                                "RG406H": {"precio_usd": 158.3, "storage": "128G", "marca": "Anbernic", "screen": "4in 960x720", "cpu": "T820", "battery": "5000mAh"},
                                "RG556": {"precio_usd": 182.6, "storage": "128G", "marca": "Anbernic", "screen": "5.48in AMOLED", "cpu": "T820", "battery": "—"},
                                "RG477M": {"precio_usd": 288.7, "storage": "256G", "marca": "Anbernic", "screen": "4.7in 1280x960", "cpu": "T820", "battery": "5300mAh"},
                            },
                        }
                    }
                }

        prov_data = st.session_state.proveedores_data
        suppliers = prov_data.get("suppliers", {})

        _n_sups = len(suppliers)
        _n_prods = sum(len(s.get("productos", {})) for s in suppliers.values())
        st.markdown(
            f'<div class="prov-page-header">'
            f'<span class="prov-page-title">Proveedores</span>'
            f'<span class="prov-stat-pill">{_n_sups} activos</span>'
            f'<span class="prov-stat-pill">{_n_prods} productos</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ════════════════════════════════════════════════════════════════════
        # SECCIÓN 1: CATÁLOGOS
        # ════════════════════════════════════════════════════════════════════
        st.markdown('<div class="prov-section">Catálogos</div>', unsafe_allow_html=True)

        def _parse_uploaded_to_products(uploaded_file) -> dict:
            """Parsea un archivo subido (CSV/Excel/PDF/PPTX) y devuelve dict de productos."""
            ext = uploaded_file.name.lower()
            raw_rows = []

            if ext.endswith(".pptx"):
                raw_rows = parse_pptx_catalog(uploaded_file.read())

            elif ext.endswith(".pdf"):
                try:
                    import pdfplumber
                    with pdfplumber.open(uploaded_file) as pdf:
                        all_tables = []
                        for page in pdf.pages:
                            all_tables.extend(page.extract_tables())

                    # Auto-detectar formato: Anbernic (EXW SZ) vs Anne/Qbuy (Price(USD))
                    def _detect_pdf_format(tables):
                        for table in tables:
                            for row in table:
                                if not row:
                                    continue
                                cells = [str(c).strip().lower() if c else "" for c in row]
                                row_text = " ".join(cells)
                                if "exw" in row_text:
                                    return "anbernic"
                                if "price(usd)" in row_text or "speicification" in row_text or "specification" in row_text:
                                    return "anne"
                        return "anne"  # default

                    pdf_format = _detect_pdf_format(all_tables)

                    if pdf_format == "anbernic":
                        # Formato Anbernic: header solo en página 1, resto son filas de datos directas
                        # ITEM | Specification | Pictures | OEM (MOQ) | MOQ (pcs) | EXW SZ | Quotation Mode | Package
                        import re as _re
                        item_col, price_col = 0, 5  # defaults confirmados por el header de pag 1
                        # Buscar header para confirmar índices de columnas
                        for table in all_tables:
                            for row in table:
                                if not row:
                                    continue
                                cells_lower = [str(c).strip().lower() if c else "" for c in row]
                                if any("exw" in c for c in cells_lower):
                                    for i, c in enumerate(cells_lower):
                                        if c == "item":
                                            item_col = i
                                        if "exw" in c:
                                            price_col = i
                                    break
                            else:
                                continue
                            break

                        SKIP_VALUES = {"item", ""}
                        # Regex para variantes con label: "8+128GB: US$201.5" o "US$29.00"
                        VARIANT_RE = _re.compile(r'^(.+?):\s*(?:US)?\$([\d,]+\.?\d*)$')
                        PLAIN_RE = _re.compile(r'(?:US)?\$([\d,]+\.?\d*)')
                        for table in all_tables:
                            for row in table:
                                if not row:
                                    continue
                                cells = [str(c).strip() if c else "" for c in row]
                                model = cells[item_col] if item_col < len(cells) else ""
                                price_raw = cells[price_col] if price_col < len(cells) else ""
                                if not model or not price_raw:
                                    continue
                                model_clean = model.split("\n")[0].strip()
                                if model_clean.lower() in SKIP_VALUES:
                                    continue
                                # Separar por línea: cada línea puede ser una variante
                                for line in price_raw.split("\n"):
                                    line = line.strip()
                                    if not line:
                                        continue
                                    vm = VARIANT_RE.match(line)
                                    if vm:
                                        # "8+128GB: US$201.5" → producto "RG 477V 8+128GB"
                                        label = vm.group(1).strip()
                                        price_str = vm.group(2).replace(",", "")
                                        product_name = f"{model_clean} {label}"
                                    else:
                                        pm = PLAIN_RE.search(line)
                                        if not pm:
                                            continue
                                        price_str = pm.group(1).replace(",", "")
                                        product_name = model_clean
                                    try:
                                        val = float(price_str)
                                        if 1 < val < 5000:
                                            raw_rows.append({
                                                "Producto": product_name,
                                                "FOB (USD)": val,
                                                "Marca": "Anbernic", "Pantalla": "—", "CPU": "—", "Storage": "—",
                                            })
                                    except ValueError:
                                        pass

                    else:
                        # Formato Anne (Qbuy): cada producto ocupa 2 filas en la tabla:
                        #   Fila header: [model_name, "Speicification", "Color", "Price(USD)", ""]
                        #   Fila data:   [""/None,    specs_text,       colores, precio,       storage]
                        current_model = None
                        SPEC_KEYWORDS = {"speicification", "specification", "price(usd)", "color"}
                        for table in all_tables:
                            for row in table:
                                if not row:
                                    continue
                                cells = [str(c).strip() if c else "" for c in row]
                                col0 = cells[0] if cells else ""
                                col1 = cells[1].lower() if len(cells) > 1 else ""
                                col3 = cells[3] if len(cells) > 3 else ""
                                col4 = cells[4] if len(cells) > 4 else ""

                                if col0 and any(kw in col1 for kw in SPEC_KEYWORDS):
                                    current_model = col0.split("\n")[0].strip()
                                    continue

                                if current_model and not col0:
                                    try:
                                        val = float(col3.replace("$", "").replace(",", "").strip())
                                        if 1 < val < 5000:
                                            storage = col4.strip() if col4.strip() else "—"
                                            # Agregar sufijo de variante SOLO cuando corresponde:
                                            # 1. El spec lista múltiples configs: "8g+128g, 12g+256g" → 2 pares
                                            # 2. Modelos conocidos multi-variante con spec en formato separado
                                            import re as _re2
                                            # Modelos Anbernic que tienen 2 variantes de RAM+storage
                                            KNOWN_MULTI_VARIANT = {"RG477M", "RG 477M"}
                                            spec_lower = col1.lower()
                                            model_key = _re2.sub(r'\s+', '', current_model).upper()
                                            pairs = _re2.findall(r'(\d+)\s*gb?\s*\+\s*(\d+)\s*gb?', spec_lower)
                                            if len(pairs) > 1:
                                                # Múltiples variantes explícitas en el spec → tomar la mayor
                                                ram, stor = pairs[-1]
                                                product_name = f"{current_model} {ram}+{stor}GB"
                                            elif current_model in KNOWN_MULTI_VARIANT or model_key in {_re2.sub(r'\s+', '', m).upper() for m in KNOWN_MULTI_VARIANT}:
                                                # Modelo multi-variante con spec en formato "12GB...256G"
                                                ram_m = _re2.search(r'(\d+)\s*gb\b', spec_lower)
                                                stor_m = _re2.search(r'\b(\d{2,3})\s*g\b', spec_lower)
                                                if ram_m and stor_m:
                                                    product_name = f"{current_model} {ram_m.group(1)}+{stor_m.group(1)}GB"
                                                else:
                                                    product_name = current_model
                                            else:
                                                product_name = current_model
                                            raw_rows.append({
                                                "Producto": product_name,
                                                "FOB (USD)": val,
                                                "Marca": "—", "Pantalla": "—", "CPU": "—", "Storage": storage,
                                            })
                                            current_model = None
                                    except ValueError:
                                        pass

                except ImportError:
                    st.warning("⚠️ `pdfplumber` no instalado. Usá CSV/Excel en su lugar.")
                    return {}

            elif ext.endswith((".csv", ".tsv")):
                sep = "\t" if ext.endswith(".tsv") else ","
                df_up = pd.read_csv(uploaded_file, sep=sep)
                cols = df_up.columns.tolist()
                col_nombre = cols[0] if cols else None
                col_precio = cols[1] if len(cols) > 1 else None
                if col_nombre and col_precio:
                    for _, r in df_up.iterrows():
                        try:
                            precio = float(str(r[col_precio]).replace("$", "").replace(",", ""))
                        except Exception:
                            continue
                        if str(r[col_nombre]).strip() and precio > 0:
                            raw_rows.append({
                                "Producto": str(r[col_nombre]).strip(),
                                "FOB (USD)": precio,
                                "Marca": str(r.get("marca", r.get("Marca", "—"))).strip(),
                                "Pantalla": "—", "CPU": "—", "Storage": "—",
                            })

            elif ext.endswith((".xlsx", ".xls")):
                df_up = pd.read_excel(uploaded_file)
                cols = df_up.columns.tolist()
                col_nombre = cols[0] if cols else None
                col_precio = cols[1] if len(cols) > 1 else None
                if col_nombre and col_precio:
                    for _, r in df_up.iterrows():
                        try:
                            precio = float(str(r[col_precio]).replace("$", "").replace(",", ""))
                        except Exception:
                            continue
                        if str(r[col_nombre]).strip() and precio > 0:
                            raw_rows.append({
                                "Producto": str(r[col_nombre]).strip(),
                                "FOB (USD)": precio,
                                "Marca": str(r.get("marca", r.get("Marca", "—"))).strip(),
                                "Pantalla": "—", "CPU": "—", "Storage": "—",
                            })

            # Convertir raw_rows a dict de productos (deduplicar por nombre)
            products = {}
            for row in raw_rows:
                nombre = row.get("Producto", "").strip()
                precio = float(row.get("FOB (USD)", 0))
                if nombre and precio > 0 and nombre not in products:
                    products[nombre] = {
                        "precio_usd": precio,
                        "marca": row.get("Marca", "—"),
                        "screen": row.get("Pantalla", "—"),
                        "cpu": row.get("CPU", "—"),
                        "storage": row.get("Storage", "—"),
                        "battery": "—",
                    }
            return products

        # Mostrar cada proveedor con su catálogo y opción de reemplazo
        for sup_name in list(suppliers.keys()):
            sup_data = suppliers[sup_name]
            updated = sup_data.get("updated_at", "") or "Sin fecha"
            prod_count = len(sup_data.get("productos", {}))

            with st.expander(f"**{sup_name}** — {prod_count} productos · {updated}"):
                contacto = sup_data.get("contacto", "—")
                web = sup_data.get("web", "—")
                st.markdown(
                    f'<div class="sup-contact">'
                    f'<span>📞 {contacto}</span>'
                    f'<span>🌐 {web}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                if sup_data.get("productos"):
                    _BRAND_CSS = {
                        "Anbernic": "brand-anbernic", "Powkiddy": "brand-powkiddy",
                        "Trimui": "brand-trimui", "Miyoo": "brand-miyoo", "Retroid": "brand-retroid",
                    }
                    productos_sorted = sorted(
                        sup_data["productos"].items(),
                        key=lambda x: float(x[1].get("precio_usd", 0)),
                    )
                    rows_html = ""
                    for _pname, _pinfo in productos_sorted:
                        _precio = float(_pinfo.get("precio_usd", 0))
                        _marca = _pinfo.get("marca", "—")
                        if _marca == "—":
                            _marca = _get_brand(_pname)
                        _storage = _pinfo.get("storage", "—")
                        _bcss = _BRAND_CSS.get(_marca, "")
                        _marca_html = f'<span class="brand-tag {_bcss}">{_marca}</span>' if _marca != "—" else '<span style="color:#374151">—</span>'
                        rows_html += (
                            f"<tr>"
                            f'<td class="pn">{_pname}</td>'
                            f"<td>{_marca_html}</td>"
                            f"<td>{_storage}</td>"
                            f'<td class="pr">${_precio:.1f}</td>'
                            f"</tr>"
                        )
                    st.markdown(
                        f'<table class="cat-tbl">'
                        f"<thead><tr>"
                        f"<th>Producto</th><th>Marca</th><th>Storage</th><th class='r'>FOB (USD)</th>"
                        f"</tr></thead>"
                        f"<tbody>{rows_html}</tbody>"
                        f"</table>",
                        unsafe_allow_html=True,
                    )

                st.markdown("**Actualizar catálogo** — reemplaza la lista anterior completa")
                uploaded = st.file_uploader(
                    f"Nueva lista de precios ({sup_name})",
                    type=["csv", "xlsx", "xls", "pdf", "pptx"],
                    key=f"upload_replace_{sup_name}",
                )

                if uploaded:
                    try:
                        new_products = _parse_uploaded_to_products(uploaded)
                    except Exception as e:
                        st.error(f"Error procesando archivo: {e}")
                        new_products = {}

                    if new_products:
                        st.success(f"✅ {len(new_products)} productos leídos del archivo")
                        old_products = sup_data.get("productos", {})
                        diff = compute_catalog_diff(old_products, new_products)

                        if diff:
                            st.markdown("**Cambios respecto al catálogo actual:**")
                            emoji_map = {"cambiado": "🟡", "nuevo": "🟢", "eliminado": "🔴"}
                            df_diff = pd.DataFrame(diff)
                            df_diff.insert(0, "", df_diff["tipo"].map(emoji_map))
                            df_diff = df_diff.drop(columns=["tipo"])
                            fmt_diff = {}
                            if "Antes (USD)" in df_diff.columns:
                                fmt_diff["Antes (USD)"] = lambda x: f"${x:.1f}" if x is not None and not pd.isna(x) else "—"
                            if "Después (USD)" in df_diff.columns:
                                fmt_diff["Después (USD)"] = lambda x: f"${x:.1f}" if x is not None and not pd.isna(x) else "—"
                            st.dataframe(df_diff, use_container_width=True, hide_index=True)
                        else:
                            st.info("Sin cambios de precio respecto al catálogo anterior.")

                        if st.button(
                            f"✅ Confirmar reemplazo — {sup_name}",
                            key=f"confirm_replace_{sup_name}",
                            type="primary",
                        ):
                            suppliers[sup_name]["productos"] = new_products
                            suppliers[sup_name]["updated_at"] = str(_date.today())
                            prov_data["suppliers"] = suppliers
                            st.session_state.proveedores_data = prov_data
                            gs_write("Proveedores", prov_data)
                            st.success(f"✅ Catálogo de {sup_name} actualizado ({len(new_products)} productos)")
                            st.rerun()
                    else:
                        st.warning("No se encontraron productos válidos en el archivo.")

                col_del1, col_del2 = st.columns([4, 1])
                with col_del2:
                    if st.button("🗑️ Eliminar proveedor", key=f"del_{sup_name}"):
                        del suppliers[sup_name]
                        prov_data["suppliers"] = suppliers
                        st.session_state.proveedores_data = prov_data
                        gs_write("Proveedores", prov_data)
                        st.rerun()

        # Agregar nuevo proveedor
        with st.expander("➕ Agregar nuevo proveedor"):
            with st.form("form_nuevo_proveedor"):
                np1, np2 = st.columns(2)
                nuevo_prov_nombre = np1.text_input("Nombre del proveedor")
                nuevo_prov_contacto = np2.text_input("Contacto (WhatsApp, email, etc)")
                nuevo_prov_web = st.text_input("Web / Alibaba", "")
                submit_prov = st.form_submit_button("➕ Crear proveedor", use_container_width=True)
                if submit_prov and nuevo_prov_nombre:
                    if nuevo_prov_nombre not in suppliers:
                        suppliers[nuevo_prov_nombre] = {
                            "contacto": nuevo_prov_contacto,
                            "web": nuevo_prov_web,
                            "updated_at": "",
                            "productos": {},
                        }
                        prov_data["suppliers"] = suppliers
                        st.session_state.proveedores_data = prov_data
                        gs_write("Proveedores", prov_data)
                        st.success(f"✅ Proveedor '{nuevo_prov_nombre}' creado")
                        st.rerun()
                    else:
                        st.warning("Ya existe un proveedor con ese nombre.")

        # ════════════════════════════════════════════════════════════════════
        # SECCIÓN 2: COMPARADOR
        # ════════════════════════════════════════════════════════════════════
        st.markdown('<div class="prov-section">Comparador de precios</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="comp-banner">'
            '<div>'
            '<div class="comp-banner-title">⚖️ Comparador de precios</div>'
            '<div class="comp-banner-sub">Todos los catálogos en una tabla. Verde = más barato entre proveedores.</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        @st.fragment
        def _render_comparador(suppliers_snap):
            if len(suppliers_snap) < 1:
                st.info("Cargá al menos un proveedor para ver la comparación.")
                return

            _col_search, _col_stock = st.columns([3, 1])
            buscar = _col_search.text_input(
                "🔍 Buscar producto", key="search_comparador",
                placeholder="ej: RG35, Trimui, 477…"
            )
            solo_stock = _col_stock.checkbox(
                "🏪 Solo mis productos", key="comp_solo_stock",
                help="Muestra solo los productos que ya tenés en TiendaNube (con o sin stock)"
            )
            df_fuzzy = fuzzy_group_products(suppliers_snap)

            if df_fuzzy.empty:
                st.info("No hay productos cargados en los catálogos.")
                return

            # Buscar solo cuando no hay filtro TN (si hay filtro TN, se aplica al final)
            if buscar and not solo_stock:
                df_fuzzy = df_fuzzy[
                    df_fuzzy["Producto"].str.contains(buscar, case=False, na=False)
                ]

            # Filtro "Solo mis productos" — construye DESDE TN + datos CRUDOS del proveedor
            # NO usa fuzzy_group_products (que fusiona productos distintos como RG40XXH/V)
            if solo_stock:
                with st.spinner("Consultando TiendaNube…"):
                    _stock_dict = get_stock_for_planner()

                if _stock_dict:
                    _EXCLUIR   = ("estuche", "funda", "case", "protector", "cable", "adaptador")
                    _MARCAS_TN = ("anbernic", "powkiddy", "miyoo", "trimui", "retroid")

                    # Lista de consolas en TN (sin accesorios)
                    _tn_consolas = sorted([
                        tn_name for tn_name in _stock_dict
                        if any(m in tn_name.lower() for m in _MARCAS_TN)
                        and not any(tn_name.lower().startswith(e) for e in _EXCLUIR)
                    ])

                    # ── Leer datos CRUDOS de proveedores (sin fuzzy grouping) ──
                    _sup_names = list(suppliers_snap.keys())
                    # norm → {sup1: price, sup2: price, ...}
                    _raw_lookup = {}
                    for _sname, _sdata in suppliers_snap.items():
                        for _pname, _pinfo in _sdata.get("productos", {}).items():
                            try:
                                _price = float(_pinfo.get("precio_usd", 0))
                            except (TypeError, ValueError):
                                continue
                            if _price <= 0:
                                continue
                            _cl = re.sub(r'\s*\d+\+\d+\s*gb.*', '', _pname, flags=re.IGNORECASE).strip()
                            _norm = re.sub(r'[^a-z0-9]', '', _cl.lower())
                            if _norm not in _raw_lookup:
                                _raw_lookup[_norm] = {}
                            _raw_lookup[_norm][_sname] = _price

                    def _cat_variants(cat):
                        variants = [cat]
                        if cat.startswith("rg") and len(cat) > 4:
                            variants.append(cat[2:])
                        return variants

                    def _find_prices(tn_norm):
                        """Busca precios de TODOS los proveedores para un producto TN.
                        Devuelve dict {supplier: price} o {}."""
                        best_prices, best_len = {}, 0
                        for _norm, _prices in _raw_lookup.items():
                            for _v in _cat_variants(_norm):
                                if _v and _v in tn_norm and len(_v) > best_len:
                                    best_len = len(_v)
                                    best_prices = _prices
                        return best_prices

                    # Construir una fila por cada consola de TN
                    _new_rows = []
                    for _tn_name in _tn_consolas:
                        _tn_norm = re.sub(r'[^a-z0-9]', '', _tn_name.lower())
                        _prices = _find_prices(_tn_norm)
                        _new_rows.append({
                            "Producto": _tn_name,
                            **{s: _prices.get(s) for s in _sup_names}
                        })

                    df_fuzzy = pd.DataFrame(_new_rows).reset_index(drop=True)

                    if buscar:
                        df_fuzzy = df_fuzzy[
                            df_fuzzy["Producto"].str.contains(buscar, case=False, na=False)
                        ]
                else:
                    st.caption("⚠️ No se pudo conectar con Tienda Nube.")

            if df_fuzzy.empty:
                st.info("No se encontraron productos con ese filtro.")
                return

            sup_cols = [c for c in df_fuzzy.columns if c != "Producto"]
            if len(sup_cols) == 1:
                st.caption("Solo hay 1 proveedor cargado — cargá más para comparar precios.")

            # Tabla HTML custom: precios grandes, verde para el más barato
            CSS = """
            <style>
            .comp-wrap{overflow-x:auto;margin-top:8px;}
            .comp-tbl{width:100%;border-collapse:collapse;font-family:inherit;}
            .comp-tbl thead tr{border-bottom:2px solid #2d3748;}
            .comp-tbl th{padding:10px 18px;text-align:left;font-size:11px;font-weight:700;
                color:#6b7280;text-transform:uppercase;letter-spacing:.8px;}
            .comp-tbl th.pc{text-align:right;}
            .comp-tbl td{padding:11px 18px;border-bottom:1px solid #1a2030;vertical-align:middle;}
            .comp-tbl tr:hover td{background:rgba(255,255,255,0.025);}
            .pname{font-size:15px;font-weight:600;color:#e2e8f0;}
            .pval{display:block;text-align:right;font-size:20px;font-weight:700;color:#9ca3af;}
            .pval.cheap{color:#4ade80;font-size:22px;}
            .pval.none{font-size:13px;color:#374151;}
            td.cheap-cell{background:rgba(20,50,20,.55);border-radius:6px;}
            </style>
            """
            _BRAND_CSS_MAP = {
                "Anbernic": "brand-anbernic", "Powkiddy": "brand-powkiddy",
                "Trimui": "brand-trimui", "Miyoo": "brand-miyoo", "Retroid": "brand-retroid",
            }
            th_prod = '<th>Producto</th>'
            th_sups = "".join(f'<th class="pc">{c}</th>' for c in sup_cols)
            rows_html = []
            for _, row in df_fuzzy.iterrows():
                prices = {c: row[c] for c in sup_cols if pd.notna(row[c]) and row[c] > 0}
                cheapest = min(prices, key=prices.get) if len(prices) > 0 else None
                brand = _get_brand(row["Producto"])
                bcss = _BRAND_CSS_MAP.get(brand, "")
                pname = row["Producto"]
                # Prefijar marca si no está ya en el nombre (evita "Trimui Trimui Brick")
                if brand != "—" and not pname.lower().startswith(brand.lower()):
                    brand_span = f'<span class="brand-tag {bcss}" style="margin-right:7px">{brand}</span>'
                    display_name = f'{brand_span}{pname}'
                else:
                    display_name = pname
                tds = f'<td><span class="pname">{display_name}</span></td>'
                for c in sup_cols:
                    v = row[c]
                    if pd.notna(v) and v > 0:
                        if c == cheapest and len(prices) > 1:
                            tds += f'<td class="cheap-cell"><span class="pval cheap">${v:.1f}</span></td>'
                        else:
                            tds += f'<td><span class="pval">${v:.1f}</span></td>'
                    else:
                        tds += '<td><span class="pval none">—</span></td>'
                rows_html.append(f"<tr>{tds}</tr>")

            tabla = (
                f'{CSS}<div class="comp-wrap"><table class="comp-tbl">'
                f"<thead><tr>{th_prod}{th_sups}</tr></thead>"
                f'<tbody>{"".join(rows_html)}</tbody>'
                f"</table></div>"
            )
            st.markdown(tabla, unsafe_allow_html=True)

            # Comparación vs CostosConsolas
            st.divider()
            st.subheader("📊 vs costos cargados en el dashboard")
            _costos_gs_prov = gs_read("CostosConsolas") or {}
            if _costos_gs_prov:
                rows_comp = []
                for _, prod_row in df_fuzzy.iterrows():
                    prod_name = prod_row["Producto"]
                    fob_dash = get_fob_usd(prod_name, _costos_gs_prov)
                    prices_prov = {c: prod_row[c] for c in sup_cols if pd.notna(prod_row[c])}
                    if not prices_prov or fob_dash <= 0:
                        continue
                    best_sup = min(prices_prov, key=prices_prov.get)
                    fob_prov = prices_prov[best_sup]
                    diff_val = round(fob_prov - fob_dash, 2)
                    rows_comp.append({
                        "Producto": prod_name,
                        "FOB Dashboard (USD)": fob_dash,
                        "Mejor proveedor": f"{best_sup} ${fob_prov:.1f}",
                        "Diferencia (USD)": diff_val,
                        "Status": "✅ Más barato" if diff_val < -0.5 else ("⚠️ Más caro" if diff_val > 0.5 else "≈ Similar"),
                    })
                if rows_comp:
                    df_vs = pd.DataFrame(rows_comp).sort_values("Diferencia (USD)")
                    st.dataframe(
                        df_vs.style.format({"FOB Dashboard (USD)": "${:.2f}", "Diferencia (USD)": "${:+.2f}"}),
                        use_container_width=True, hide_index=True,
                    )
                else:
                    st.info("No hay coincidencias entre catálogos y costos del dashboard.")
            else:
                st.info("Cargá costos en 💻 Costos de consolas para comparar.")

        _render_comparador(suppliers)

        # ════════════════════════════════════════════════════════════════════
        # SECCIÓN 3: PLANIFICADOR DE COMPRA
        # ════════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("🛒 Planificador de compra")
        st.caption("Cruzá tu stock actual con los precios de los catálogos. Seleccioná qué reponer y generá el resumen del pedido por proveedor.")

        if not suppliers:
            st.info("Cargá al menos un proveedor para usar el planificador.")
        else:
            if st.button("🔄 Cargar stock desde Tienda Nube", key="btn_load_stock_planner"):
                with st.spinner("Consultando stock..."):
                    st.session_state.stock_planner = get_stock_for_planner()
                st.success(f"✅ {len(st.session_state.stock_planner)} productos cargados")

            if "stock_planner" not in st.session_state:
                st.info("Hacé clic en 'Cargar stock' para ver los niveles actuales.")
            else:
                from difflib import SequenceMatcher as _SM

                stock_dict = st.session_state.stock_planner

                def _best_stock_match(prod_name: str, stock_dict: dict) -> int | None:
                    """Busca el stock en TN usando fuzzy match. None = sin límite / no encontrado."""
                    best_ratio = 0.0
                    best_val = None
                    for tn_name, tn_stock in stock_dict.items():
                        ratio = _SM(None, _normalizar(prod_name), _normalizar(tn_name)).ratio()
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_val = tn_stock
                    return best_val if best_ratio >= 0.70 else "?"

                def _best_supplier_price(prod_name: str, suppliers: dict) -> tuple[str, float]:
                    """Devuelve (proveedor, precio) del proveedor más barato para ese producto."""
                    candidates = []
                    for sup_name, sup_data in suppliers.items():
                        best_ratio_sup = 0.0
                        best_price_sup = 0.0
                        for p_name, p_info in sup_data.get("productos", {}).items():
                            ratio = _SM(None, _normalizar(prod_name), _normalizar(p_name)).ratio()
                            if ratio >= 0.80 and ratio > best_ratio_sup:
                                best_ratio_sup = ratio
                                best_price_sup = float(p_info.get("precio_usd", 0))
                        if best_ratio_sup >= 0.80:
                            candidates.append((sup_name, best_price_sup))
                    if not candidates:
                        return ("—", 0.0)
                    return min(candidates, key=lambda x: x[1])

                # Construir tabla del planificador (un producto por fila, sin duplicados)
                seen_products: set = set()
                plan_rows = []
                for sup_name, sup_data in suppliers.items():
                    for prod_name in sup_data.get("productos", {}).keys():
                        canonical = _normalizar(prod_name)
                        if canonical in seen_products:
                            continue
                        seen_products.add(canonical)

                        stock_val = _best_stock_match(prod_name, stock_dict)
                        best_sup, best_price = _best_supplier_price(prod_name, suppliers)

                        if isinstance(stock_val, int):
                            urgency = "🔴 Crítico" if stock_val <= 2 else ("🟡 Bajo" if stock_val <= 5 else "🟢 OK")
                        elif stock_val is None:
                            urgency = "♾️ Sin límite"
                        else:
                            urgency = "❓ Sin dato"

                        if best_sup == "—":
                            continue
                        plan_rows.append({
                            "Producto": prod_name,
                            "Stock": stock_val if stock_val not in (None, "?") else ("Sin límite" if stock_val is None else "—"),
                            "Urgencia": urgency,
                            "Mejor precio (USD)": best_price,
                            "Proveedor sugerido": best_sup,
                            "Comprar": False,
                            "Cantidad": 1,
                        })

                if not plan_rows:
                    st.info("No hay productos en los catálogos cargados.")
                else:
                    # Ordenar por urgencia (Crítico primero)
                    urgency_order = {"🔴 Crítico": 0, "🟡 Bajo": 1, "🟢 OK": 2, "❓ Sin dato": 3, "♾️ Sin límite": 4}
                    plan_rows.sort(key=lambda r: urgency_order.get(r["Urgencia"], 5))

                    df_plan = pd.DataFrame(plan_rows)
                    edited_plan = st.data_editor(
                        df_plan,
                        column_config={
                            "Comprar": st.column_config.CheckboxColumn("✓ Comprar", default=False),
                            "Cantidad": st.column_config.NumberColumn("Cant.", min_value=1, step=1, default=1),
                            "Mejor precio (USD)": st.column_config.NumberColumn("Precio (USD)", format="$%.1f", disabled=True),
                            "Producto": st.column_config.TextColumn("Producto", disabled=True),
                            "Stock": st.column_config.TextColumn("Stock", disabled=True),
                            "Urgencia": st.column_config.TextColumn("Urgencia", disabled=True),
                            "Proveedor sugerido": st.column_config.TextColumn("Proveedor", disabled=True),
                        },
                        hide_index=True,
                        use_container_width=True,
                        key="plan_table",
                    )

                    selected = edited_plan[edited_plan["Comprar"] == True]
                    if not selected.empty:
                        st.divider()
                        st.subheader("📋 Resumen del pedido")

                        by_supplier: dict = {}
                        for _, row in selected.iterrows():
                            sup = str(row["Proveedor sugerido"])
                            if sup not in by_supplier:
                                by_supplier[sup] = []
                            by_supplier[sup].append({
                                "producto": str(row["Producto"]),
                                "cantidad": int(row["Cantidad"]),
                                "precio": float(row["Mejor precio (USD)"]),
                            })

                        order_text = ""
                        grand_total = 0.0
                        for sup, items in by_supplier.items():
                            subtotal = sum(i["cantidad"] * i["precio"] for i in items)
                            grand_total += subtotal
                            st.markdown(f"**📦 Pedido a {sup} — Total: ${subtotal:.0f} USD**")
                            order_text += f"Pedido a {sup} — Total: ${subtotal:.0f} USD\n"
                            for item in items:
                                line_total = item["cantidad"] * item["precio"]
                                st.markdown(f"  · {item['cantidad']}× {item['producto']} × ${item['precio']:.0f} = ${line_total:.0f}")
                                order_text += f"  · {item['cantidad']}x {item['producto']} x ${item['precio']:.0f}\n"
                            order_text += "\n"

                        st.markdown(f"**💰 Total general: ${grand_total:.0f} USD**")
                        order_text += f"Total general: ${grand_total:.0f} USD"

                        st.divider()
                        st.markdown("**Copiá esto para WhatsApp:**")
                        st.code(order_text, language=None)

        # ── Guardado global ──
        st.divider()
        if st.button("💾 Guardar todos los datos de proveedores", use_container_width=True):
            ok = gs_write("Proveedores", st.session_state.proveedores_data)
            st.success("✅ Guardado en Google Sheets" if ok else "⚠️ Solo en sesión")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 11: ANALISTA IA
    # ══════════════════════════════════════════════════════════════════════════
    with tab11:
        if "analyst_messages" not in st.session_state:
            st.session_state.analyst_messages = []

        st.subheader("🤖 Analista Financiero IA")
        st.caption(
            "Preguntale lo que quieras sobre el negocio. "
            "Usa los datos reales del período seleccionado."
        )

        if not ANTHROPIC_KEY:
            st.error(
                "⚠️ Falta la API key de Anthropic.\n\n"
                "Agregá `ANTHROPIC_KEY = \"sk-ant-...\"` en `secrets.toml`."
            )
            st.info("💡 Obtené tu key en [console.anthropic.com](https://console.anthropic.com/)")
        else:
            # ── Construir contexto de datos ──
            def _build_analyst_context():
                lines = []
                _dias_p = max((fecha_hasta - fecha_desde).days + 1, 1)
                _tc = int(dolar_blue) if dolar_blue else 1200
                _gastos_gs = gs_read("GastosFijos") or {}
                _costos_gs = gs_read("CostosConsolas") or {}

                lines.append(f"=== MARKET GAMER — ANÁLISIS FINANCIERO ===")
                lines.append(f"Período: {fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')} ({_dias_p} días)")
                lines.append(f"Tipo de cambio: ${_tc:,} ARS/USD (dólar blue)")
                lines.append("")

                if df_tn.empty:
                    lines.append("No hay órdenes cargadas en este período.")
                    return "\n".join(lines)

                _total_ordenes = len(df_tn)
                _fact_bruta = df_tn["Total ($)"].sum()
                _total_comision = df_tn["Comision PN ($)"].sum()
                _neto = df_tn["Neto cobrado ($)"].sum()
                _envios = df_tn["Envio costo ($)"].sum()
                _ticket_prom = _fact_bruta / _total_ordenes if _total_ordenes > 0 else 0

                lines.append("--- RESUMEN GENERAL ---")
                lines.append(f"Órdenes: {_total_ordenes}")
                lines.append(f"Facturación bruta: ${_fact_bruta:,.0f}")
                if _fact_bruta > 0:
                    lines.append(f"Comisiones PN: ${_total_comision:,.0f} ({_total_comision/_fact_bruta*100:.2f}%)")
                lines.append(f"Neto cobrado: ${_neto:,.0f}")
                lines.append(f"Costo envíos dueño: ${_envios:,.0f}")
                lines.append(f"Ticket promedio: ${_ticket_prom:,.0f}")
                lines.append(f"Órdenes/día: {_total_ordenes / _dias_p:.1f}")
                lines.append(f"Facturación/día: ${_fact_bruta / _dias_p:,.0f}")
                lines.append("")

                # Ventas por producto
                lines.append("--- VENTAS POR PRODUCTO ---")
                _prod_stats = {}
                for _, _row in df_tn.iterrows():
                    _prods = [p.strip() for p in str(_row.get("Productos", "")).split(" / ") if p.strip()]
                    _n = max(len(_prods), 1)
                    for _p in _prods:
                        if _p not in _prod_stats:
                            _prod_stats[_p] = {"uds": 0, "rev": 0.0, "ords": 0}
                        _prod_stats[_p]["uds"] += int(_row.get("Cantidad", 1) or 1)
                        _prod_stats[_p]["rev"] += _row.get("Total ($)", 0) / _n
                        _prod_stats[_p]["ords"] += 1

                _orders_raw = st.session_state.orders_raw
                _prod_rows = _build_product_rows_from_raw(_orders_raw) if _orders_raw else []
                _margen_map = {}
                if _prod_rows:
                    _df_pr = pd.DataFrame(_prod_rows)
                    for _pn, _grp in _df_pr.groupby("Producto"):
                        _precio_p = _grp["Precio ($)"].mean()
                        _costo_usd = get_costo_total_usd(_pn, _costos_gs)
                        _costo_ars = _costo_usd * _tc
                        _costo_full = _costo_ars + 2500 + (_precio_p * 0.105)
                        _com_p = _grp["Comisión PN ($)"].mean()
                        _env_p = _grp["Envío ($)"].mean()
                        _margen_p = _precio_p - _costo_full - _com_p - _env_p
                        _margen_pct = (_margen_p / _precio_p * 100) if _precio_p > 0 else 0
                        _margen_map[_pn] = {
                            "precio": _precio_p, "costo_usd": _costo_usd,
                            "costo_full": _costo_full, "margen": _margen_p, "margen_pct": _margen_pct,
                        }

                lines.append(f"{'Producto':<45} {'Uds':>5} {'Revenue':>12} {'Margen%':>8} {'FOB$':>7}")
                lines.append("-" * 82)
                for _pn, _ps in sorted(_prod_stats.items(), key=lambda x: x[1]["rev"], reverse=True):
                    _mi = _margen_map.get(_pn, {})
                    _mpct = f"{_mi.get('margen_pct', 0):.1f}%" if _mi else "s/d"
                    _fob = f"${_mi.get('costo_usd', 0):.0f}" if _mi.get('costo_usd') else "s/d"
                    lines.append(f"{_pn:<45} {_ps['uds']:>5} ${_ps['rev']:>10,.0f} {_mpct:>8} {_fob:>7}")
                lines.append("")

                # Evolución diaria
                lines.append("--- EVOLUCIÓN DIARIA ---")
                _df_dia = df_tn.groupby("Fecha").agg(
                    Ordenes=("Orden", "count"), Facturacion=("Total ($)", "sum"), Unidades=("Cantidad", "sum"),
                ).reset_index().sort_values("Fecha")
                for _, _r in _df_dia.iterrows():
                    lines.append(f"{_r['Fecha']:<12} {int(_r['Ordenes']):>5} órd  ${_r['Facturacion']:>12,.0f}  {int(_r['Unidades']):>4} uds")
                if len(_df_dia) >= 6:
                    _1h = _df_dia.head(len(_df_dia) // 2)["Facturacion"].mean()
                    _2h = _df_dia.tail(len(_df_dia) // 2)["Facturacion"].mean()
                    if _2h > _1h * 1.1:
                        lines.append(f"📈 TENDENCIA ALCISTA (+{(_2h/_1h - 1)*100:.0f}%)")
                    elif _2h < _1h * 0.9:
                        lines.append(f"📉 TENDENCIA BAJISTA ({(_2h/_1h - 1)*100:.0f}%)")
                    else:
                        lines.append("➡️ TENDENCIA ESTABLE")
                lines.append("")

                # Medios de pago
                lines.append("--- MEDIOS DE PAGO ---")
                _med = df_tn.groupby("Medio de Pago").agg(
                    Ordenes=("Orden", "count"), Fact=("Total ($)", "sum"), Com=("Comision PN ($)", "sum"),
                ).reset_index().sort_values("Fact", ascending=False)
                for _, _r in _med.iterrows():
                    _cp = (_r["Com"] / _r["Fact"] * 100) if _r["Fact"] > 0 else 0
                    lines.append(f"{_r['Medio de Pago']:<25} {int(_r['Ordenes']):>5} órd  ${_r['Fact']:>12,.0f}  com {_cp:.2f}%")
                lines.append("")

                # Cuotas
                lines.append("--- DISTRIBUCIÓN POR CUOTAS ---")
                _cuotas = df_tn.groupby("Cuotas").agg(Ordenes=("Orden", "count"), Fact=("Total ($)", "sum")).reset_index()
                for _, _r in _cuotas.iterrows():
                    lines.append(f"  {int(_r['Cuotas'])} cuota(s): {int(_r['Ordenes'])} órdenes — ${_r['Fact']:,.0f}")
                lines.append("")

                # Gastos fijos
                lines.append("--- GASTOS FIJOS MENSUALES ---")
                _total_gf = 0
                if _gastos_gs:
                    for _k, _v in _gastos_gs.items():
                        if isinstance(_v, (int, float)) and _v > 0:
                            lines.append(f"  {_k}: ${_v:,.0f}")
                            _total_gf += _v
                    lines.append(f"  TOTAL mensual: ${_total_gf:,.0f}")
                    lines.append(f"  Prorrateado ({_dias_p}d): ${round(_total_gf * _dias_p / 30):,.0f}")
                lines.append("")

                # Resultado financiero
                lines.append("--- RESULTADO FINANCIERO ---")
                _costo_prods = 0
                for _pn, _ps in _prod_stats.items():
                    _costo_prods += get_costo_total_usd(_pn, _costos_gs) * _tc * _ps["uds"]
                _iva = _fact_bruta * 0.105
                _gf_per = round(_total_gf * _dias_p / 30)
                _margen_b = _neto - _costo_prods - _envios
                _resultado = _margen_b - _iva - _gf_per

                lines.append(f"  Facturación bruta:  ${_fact_bruta:>12,.0f}")
                lines.append(f"  - Comisiones PN:    ${_total_comision:>12,.0f}")
                lines.append(f"  = Neto cobrado:     ${_neto:>12,.0f}")
                lines.append(f"  - Costo productos:  ${_costo_prods:>12,.0f}")
                lines.append(f"  - Costo envíos:     ${_envios:>12,.0f}")
                lines.append(f"  = Margen bruto:     ${_margen_b:>12,.0f}")
                lines.append(f"  - IVA (10.5%):      ${_iva:>12,.0f}")
                lines.append(f"  - Gastos fijos:     ${_gf_per:>12,.0f}")
                lines.append(f"  = RESULTADO:        ${_resultado:>12,.0f} {'✅' if _resultado >= 0 else '🔴'}")
                if _fact_bruta > 0:
                    lines.append(f"  Margen neto/bruto:  {_resultado/_fact_bruta*100:.1f}%")
                lines.append("")

                # Stock
                _stock_df = st.session_state.get("stock_tn")
                if _stock_df is not None and not _stock_df.empty:
                    lines.append("--- STOCK ACTUAL ---")
                    _stock_sum = _stock_df.groupby("Producto").agg(
                        Stock=("Stock", lambda x: sum(v for v in x if isinstance(v, (int, float)))),
                    ).reset_index().sort_values("Stock")
                    for _, _r in _stock_sum.iterrows():
                        _pn = _r["Producto"]
                        _st = int(_r["Stock"])
                        _vel = _prod_stats.get(_pn, {}).get("uds", 0) / _dias_p
                        _dr = int(_st / _vel) if _vel > 0 else 999
                        _alert = " ⚠️" if _dr <= 14 else ""
                        lines.append(f"{_pn:<45} stock:{_st:>4}  vel:{_vel:.2f}/día  {_dr}d{_alert}")
                    lines.append("")

                # Costos cargados
                if _costos_gs:
                    lines.append("--- COSTOS DE CONSOLAS ---")
                    _ckg = float(_costos_gs.get("_costo_kg_usd", 65.0) or 65.0)
                    for _k, _v in sorted(_costos_gs.items()):
                        if _k.startswith("_") or not isinstance(_v, dict):
                            continue
                        _fob = float(_v.get("fob_usd", 0) or 0)
                        _tot = float(_v.get("costo_total_usd", 0) or 0)
                        if _tot == 0 and _fob > 0:
                            _tot = _fob + float(_v.get("peso_kg", 0) or 0) * _ckg
                        if _fob > 0:
                            lines.append(f"{_k:<40} FOB ${_fob:.0f}  Total ${_tot:.0f}  ARS ${_tot*_tc:,.0f}")
                    lines.append("")

                # Top clientes
                lines.append("--- TOP 10 CLIENTES ---")
                _top_cli = df_tn.groupby("Cliente").agg(
                    Ords=("Orden", "count"), Fact=("Total ($)", "sum"),
                ).reset_index().sort_values("Fact", ascending=False).head(10)
                for _, _r in _top_cli.iterrows():
                    lines.append(f"  {_r['Cliente']}: {int(_r['Ords'])} ord — ${_r['Fact']:,.0f}")
                lines.append("")

                # Días de la semana
                lines.append("--- VENTAS POR DÍA DE SEMANA ---")
                try:
                    _dfw = df_tn.copy()
                    _dfw["DOW"] = pd.to_datetime(_dfw["Fecha"]).dt.day_name()
                    _labels = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
                               "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"}
                    _dow = _dfw.groupby("DOW").agg(Ords=("Orden", "count"), Fact=("Total ($)", "sum")).reset_index()
                    _dow["DOW"] = pd.Categorical(_dow["DOW"], categories=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"], ordered=True)
                    for _, _r in _dow.sort_values("DOW").iterrows():
                        lines.append(f"  {_labels.get(_r['DOW'], _r['DOW'])}: {int(_r['Ords'])} órd — ${_r['Fact']:,.0f}")
                except Exception:
                    pass

                return "\n".join(lines)

            # ── Llamar a Claude API ──
            def _call_analyst(question, history=None):
                context = _build_analyst_context()
                system_prompt = f"""Sos el analista financiero de Market Gamer, un e-commerce argentino de consolas retro portátiles (Anbernic, Powkiddy, Trimui, Miyoo).

Tu trabajo es analizar los datos del negocio y dar insights accionables. Respondé en español argentino, directo y sin relleno.

REGLAS:
- Basate EXCLUSIVAMENTE en los datos proporcionados. No inventes números.
- Formato argentino para montos ($XXX.XXX).
- Detectá problemas y oportunidades con recomendaciones concretas.
- Si no hay datos suficientes, decilo.
- Priorizá insights accionables sobre descripciones obvias.
- Emojis para alertas: 🔴 problema, 🟡 atención, 🟢 bien, 💡 oportunidad.
- Si piden análisis general: performance, productos estrella, alertas, medios de pago, 3 recomendaciones.

DATOS DEL NEGOCIO:
{context}"""

                messages = []
                if history:
                    for msg in history:
                        messages.append({"role": msg["role"], "content": msg["content"]})
                messages.append({"role": "user", "content": question})

                try:
                    response = requests.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "Content-Type": "application/json",
                            "x-api-key": ANTHROPIC_KEY,
                            "anthropic-version": "2023-06-01",
                        },
                        json={
                            "model": "claude-sonnet-4-20250514",
                            "max_tokens": 4096,
                            "system": system_prompt,
                            "messages": messages,
                        },
                        timeout=60,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return data["content"][0]["text"]
                    elif response.status_code == 401:
                        return "🔴 API key inválida. Revisá ANTHROPIC_KEY en secrets."
                    elif response.status_code == 429:
                        return "🟡 Rate limit. Esperá unos segundos."
                    else:
                        return f"🔴 Error ({response.status_code}): {response.text[:200]}"
                except requests.exceptions.Timeout:
                    return "🟡 Timeout. Probá con algo más específico."
                except Exception as e:
                    return f"🔴 Error de conexión: {str(e)}"

            # ── Preguntas rápidas predefinidas ──
            PREGUNTAS_RAPIDAS = {
                "📊 Resumen ejecutivo": (
                    "Haceme un resumen ejecutivo completo del período. Incluí: "
                    "1) Performance general (facturación, tendencia, ticket promedio), "
                    "2) Top 5 productos por revenue y por margen, "
                    "3) Alertas críticas (stock, márgenes negativos, productos que no se venden), "
                    "4) Análisis de medios de pago y su impacto en rentabilidad, "
                    "5) 3 recomendaciones priorizadas con impacto estimado."
                ),
                "🏆 Productos estrella": (
                    "Clasificá los productos en: ESTRELLAS (alto volumen + alto margen), "
                    "VACAS (alto volumen + bajo margen), OPORTUNIDADES (bajo volumen + alto margen), "
                    "PERROS (bajo volumen + bajo margen). Para cada uno, qué acción tomar."
                ),
                "💳 Impacto cuotas": (
                    "Analizá cómo los medios de pago impactan en rentabilidad: "
                    "% en cuotas vs débito, margen perdido por cuotas, productos con margen negativo en cuotas, "
                    "y si conviene incentivar transferencia/débito con descuento."
                ),
                "📦 Riesgo stock": (
                    "Analizá riesgo de stock: qué se agota primero, sobrestock, "
                    "qué pedir urgente con cantidades para 30 días."
                ),
                "📈 Tendencia": (
                    "Analizá tendencias: ventas subiendo/bajando, mejores días de semana, "
                    "productos ganando/perdiendo tracción, proyección mensual, "
                    "órdenes/día necesarias para cubrir gastos fijos."
                ),
                "💰 Punto equilibrio": (
                    "Calculá punto de equilibrio: facturación mínima mensual, "
                    "unidades necesarias, órdenes/día mínimas, "
                    "y si estoy arriba o abajo en este período."
                ),
                "🔍 Márgenes": (
                    "Diagnóstico de márgenes: margen promedio ponderado, productos con margen <10%, "
                    "desglose top 5 (precio/costo/comisión/IVA/envío/margen), "
                    "dónde se escapa la plata, impacto de subir precios 5-10%."
                ),
            }

            # ── Preview de datos ──
            with st.expander("📋 Ver datos que recibe el analista", expanded=False):
                _ctx_preview = _build_analyst_context()
                st.text(_ctx_preview)
                st.caption(f"📏 {len(_ctx_preview)} caracteres · ~{len(_ctx_preview)//4} tokens")

            # ── Botones de análisis rápido ──
            st.markdown("### ⚡ Análisis rápidos")

            _cols1 = st.columns(4)
            _cols2 = st.columns(4)
            _all_cols = _cols1 + _cols2
            _items = list(PREGUNTAS_RAPIDAS.items())

            for _i, (_label, _question) in enumerate(_items):
                if _i < len(_all_cols):
                    with _all_cols[_i]:
                        if st.button(_label, key=f"quick_{_i}", use_container_width=True):
                            st.session_state.analyst_messages.append(
                                {"role": "user", "content": _question}
                            )
                            with st.spinner("🤖 Analizando..."):
                                _resp = _call_analyst(
                                    _question,
                                    st.session_state.analyst_messages[:-1],
                                )
                            st.session_state.analyst_messages.append(
                                {"role": "assistant", "content": _resp}
                            )
                            st.rerun()

            st.divider()

            # ── Chat ──
            st.markdown("### 💬 Conversación")

            if not st.session_state.analyst_messages:
                st.info(
                    "👆 Usá un análisis rápido o escribí tu pregunta abajo.\n\n"
                    "**Ejemplos:** *¿Cuál es mi producto más rentable?* · "
                    "*¿Cuánto me cuesta Pago Nube en promedio?* · "
                    "*¿Qué consola debería dejar de vender?* · "
                    "*Si subo precios 10%, ¿cómo cambia el resultado?*"
                )

            for _msg in st.session_state.analyst_messages:
                with st.chat_message(_msg["role"], avatar="🧑‍💼" if _msg["role"] == "user" else "🤖"):
                    st.markdown(_msg["content"])

            _user_input = st.chat_input("Preguntale al analista...")

            if _user_input:
                st.session_state.analyst_messages.append(
                    {"role": "user", "content": _user_input}
                )
                with st.chat_message("user", avatar="🧑‍💼"):
                    st.markdown(_user_input)
                with st.chat_message("assistant", avatar="🤖"):
                    with st.spinner("🤖 Analizando datos..."):
                        _resp = _call_analyst(
                            _user_input,
                            st.session_state.analyst_messages[:-1],
                        )
                    st.markdown(_resp)
                st.session_state.analyst_messages.append(
                    {"role": "assistant", "content": _resp}
                )

            # ── Controles ──
            st.divider()
            _cc1, _cc2, _cc3 = st.columns(3)
            with _cc1:
                if st.button("🗑️ Limpiar conversación", use_container_width=True):
                    st.session_state.analyst_messages = []
                    st.rerun()
            with _cc2:
                if st.session_state.analyst_messages:
                    _chat_txt = "\n\n".join(
                        f"{'👤 Bruno' if m['role'] == 'user' else '🤖 Analista'}: {m['content']}"
                        for m in st.session_state.analyst_messages
                    )
                    st.download_button(
                        "⬇️ Exportar conversación",
                        _chat_txt.encode("utf-8"),
                        f"analisis_mg_{fecha_desde}_{fecha_hasta}.txt",
                        "text/plain",
                        use_container_width=True,
                    )
            with _cc3:
                if st.button("🔄 Refrescar datos", use_container_width=True):
                    st.session_state.analyst_context = ""
                    st.rerun()

else:
    st.info("👈 Seleccioná el período en el panel izquierdo y hacé clic en Buscar.")
