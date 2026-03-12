import streamlit as st
import requests
import pandas as pd
import plotly.express as px
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
    return re.sub(r'\s+', ' ', str(s).strip().lower())

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

def calcular_costo_orden_ars(productos_str, cantidad, tipo_cambio_ars, costos_gs=None):
    prods = [p.strip() for p in str(productos_str).split(" / ") if p.strip()]
    if not prods:
        return 0.0
    if len(prods) == 1:
        return get_fob_usd(prods[0], costos_gs) * int(cantidad or 1) * tipo_cambio_ars
    return sum(get_fob_usd(p, costos_gs) * tipo_cambio_ars for p in prods)

def costo_final_row(row, tipo_cambio, costos_gs):
    costo_tn = float(row.get("Costo Productos ($)", 0) or 0)
    if costo_tn > 0:
        return round(costo_tn, 0)
    return round(calcular_costo_orden_ars(
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
    """Calcula tasas reales desde las transacciones de Pago Nube si hay datos de fees."""
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
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Dashboard",
        "🔍 Detalle y ajustes",
        "💚 Salud Financiera",
        "📦 Stock",
        "🔥 Velocidad de ventas",
        "🏗️ Gastos fijos",
        "💻 Costos de consolas",
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
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Ordenes", len(df_tn))
            k2.metric("Facturacion bruta", fmt(df_tn["Total ($)"].sum()))
            k3.metric("Comision PN", fmt(df_tn["Comision PN ($)"].sum()))
            k4.metric("Neto cobrado", fmt(df_tn["Neto cobrado ($)"].sum()))
            k5.metric("Margen total", fmt(df_tn["Margen ($)"].sum()))

            # ── Ventas por día + Top 10 por unidades ──
            col_a, col_b = st.columns(2)
            with col_a:
                fig_dia = px.bar(
                    df_tn.groupby("Fecha")["Total ($)"].sum().reset_index(),
                    x="Fecha", y="Total ($)", title="Ventas por día",
                    color_discrete_sequence=["#009EE3"],
                )
                fig_dia.update_layout(yaxis_tickformat="$,.0f")
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
                    fig_tp = px.bar(df_tp, x="Unidades", y="Producto", orientation="h",
                        title="Top 10 productos (unidades)", color_discrete_sequence=["#00C49F"])
                    fig_tp.update_layout(yaxis={"categoryorder": "total ascending"})
                    st.plotly_chart(fig_tp, use_container_width=True)

            # ── Top 10 por monto vendido ──
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
                    fig_rev = px.bar(df_rev, x="Monto ($)", y="Producto", orientation="h",
                        title="Top 10 productos (facturación $)", color_discrete_sequence=["#FFD700"])
                    fig_rev.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_tickformat="$,.0f")
                    fig_rev.update_traces(texttemplate="$%{x:,.0f}", textposition="outside")
                    st.plotly_chart(fig_rev, use_container_width=True)

            with col_rev2:
                # ── Cantidad de transacciones por medio de pago ──
                tx_medio = df_tn.groupby("Medio de Pago")["Orden"].count().reset_index()
                tx_medio.columns = ["Medio de Pago", "Transacciones"]
                tx_medio = tx_medio.sort_values("Transacciones", ascending=False)
                fig_tx = px.bar(tx_medio, x="Medio de Pago", y="Transacciones",
                    title="Transacciones por medio de pago",
                    color_discrete_sequence=["#009EE3"], text="Transacciones")
                fig_tx.update_traces(textposition="outside")
                st.plotly_chart(fig_tx, use_container_width=True)

            # ── Comisiones por medio de pago ──
            st.divider()
            st.subheader("💳 Costos Pago Nube por medio de pago")
            comis_medio = df_tn.groupby("Medio de Pago").agg(
                Ordenes=("Orden", "count"),
                Facturacion=("Total ($)", "sum"),
                Comision=("Comision PN ($)", "sum"),
            ).reset_index().sort_values("Comision", ascending=False)
            comis_medio["Costo %"] = (comis_medio["Comision"] / comis_medio["Facturacion"] * 100).round(2)

            fig_bar_com = px.bar(
                comis_medio, x="Medio de Pago", y="Comision",
                title="Monto de comisión por medio de pago",
                color="Costo %",
                color_continuous_scale=["#00C49F", "#FFD700", "#FF5733"],
                text="Comision",
            )
            fig_bar_com.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
            fig_bar_com.update_layout(yaxis_tickformat="$,.0f", coloraxis_showscale=False)
            st.plotly_chart(fig_bar_com, use_container_width=True)

            comis_fmt = comis_medio.copy()
            comis_fmt["Facturacion"] = comis_fmt["Facturacion"].apply(fmt)
            comis_fmt["Comision"] = comis_fmt["Comision"].apply(fmt)
            comis_fmt["Costo %"] = comis_fmt["Costo %"].apply(fmt_pct)
            comis_fmt.columns = ["Medio de Pago", "Órdenes", "Facturación", "Comisión PN", "Costo %"]
            st.dataframe(comis_fmt, use_container_width=True, hide_index=True)

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

        with st.expander("⚙️ Configuración", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                dolar_default = int(dolar_blue) if dolar_blue else 1200
                tipo_cambio = st.number_input(
                    f"💵 Dólar blue (auto: ${dolar_default:,.0f})" if dolar_blue else "💵 Tipo de cambio",
                    value=dolar_default, step=10,
                )
            with col2:
                pct_iva = st.slider("🧾 IVA efectivo (%)", 0.0, 21.0, 10.5, 0.5)
            with col3:
                pauta_manual = st.number_input("📣 Pauta publicitaria (ARS)", value=0, step=50_000)

        # Tasas de Pago Nube
        tasas_reales = calcular_tasas_reales(df_pagos) if not df_pagos.empty else None

        with st.expander("💳 Tasas de Pago Nube por cuotas (ajustables)", expanded=False):
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
                if "debit" in metodo or "debito" in metodo:
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
            k1.metric("Facturacion bruta", fmt(facturacion_bruta))
            k2.metric("Comisiones PN", fmt(comisiones_pn), delta=f"-{fmt(comisiones_pn)}", delta_color="inverse")
            k3.metric("Neto cobrado", fmt(neto_cobrado))
            k4.metric("Costo productos", fmt(costo_productos), delta=f"-{fmt(costo_productos)}", delta_color="inverse")
            k5.metric("Costo envios", fmt(costo_envios), delta=f"-{fmt(costo_envios)}", delta_color="inverse")

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
                    "Facturacion bruta", "Comisiones PN", "Costo productos",
                    "Costo envios", f"IVA ({pct_iva:.1f}%)", "Pauta",
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

                # Alertas
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

                # Resumen
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

                # Evolución por producto
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

        # ── Editar gastos existentes ──
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

        # Procesar eliminaciones
        if gastos_a_eliminar:
            for k in gastos_a_eliminar:
                nuevos_gastos.pop(k, None)
                st.session_state.gastos_fijos.pop(k, None)
            gs_write("GastosFijos", nuevos_gastos)
            st.session_state.gastos_fijos = nuevos_gastos
            st.rerun()

        # ── Agregar nuevo gasto ──
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

        # ── Guardar ──
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

        # ── Cargar productos de TN (merge, no overwrite) ──
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

                    # Merge: agregar productos nuevos sin sobreescribir existentes
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
                            # Solo actualizar peso si viene de TN y el guardado no tiene
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

        # Construir tabla editable de costos
        all_prods = set(productos_map.keys())
        for k in costos:
            if not k.startswith("_"):
                all_prods.add(k)

        if not all_prods:
            st.info("Cargá productos desde TN con el botón de arriba.")
        else:
            # Construir DataFrame para edición y display
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

            # Opción de orden
            orden_col = st.selectbox(
                "Ordenar por", df_costos_edit.columns.tolist(),
                index=0, key="orden_costos",
            )
            orden_asc = st.checkbox("Ascendente", value=True, key="orden_asc")
            df_costos_edit = df_costos_edit.sort_values(orden_col, ascending=orden_asc)

            # Tabla interactiva para edición
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

            # Recalcular columnas derivadas después de edición
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

            # Resumen visual
            st.divider()
            st.subheader("📊 Resumen de costos")
            st.dataframe(
                edited_df.style.format({
                    "FOB (USD)": "${:,.2f}", "Import (USD)": "${:,.2f}",
                    "Total (USD)": "${:,.2f}", "Total (ARS)": "${:,.0f}", "Peso (kg)": "{:.3f}",
                }),
                use_container_width=True, hide_index=True,
            )

else:
    st.info("👈 Seleccioná el período en el panel izquierdo y hacé clic en Buscar.")
