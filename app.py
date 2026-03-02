import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
import time
import json

TN_TOKEN = st.secrets["TN_TOKEN"]
TN_STORE_ID = st.secrets["TN_STORE_ID"]

# ── Google Sheets helper ───────────────────────────────────────────────
SHEET_ID = st.secrets.get("SHEET_ID", "1wY2KjSC8SX-nMQD7J43xrdSY0SgG8fJeL9d5I_02DdE")
GCP_CREDS = st.secrets.get("gcp_service_account", {})

@st.cache_resource
def get_gsheet_client():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(dict(GCP_CREDS), scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        return None

def gs_read(sheet_name):
    try:
        gc = get_gsheet_client()
        if not gc or not SHEET_ID: return {}
        ws = gc.open_by_key(SHEET_ID).worksheet(sheet_name)
        data = ws.get_all_values()
        if len(data) >= 2:
            return json.loads(data[1][0]) if data[1] else {}
        return {}
    except:
        return {}

def gs_write(sheet_name, data_dict):
    try:
        gc = get_gsheet_client()
        if not gc or not SHEET_ID: return False
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(sheet_name)
        except:
            ws = sh.add_worksheet(sheet_name, rows=10, cols=2)
        ws.clear()
        ws.update("A1", [["key"], [json.dumps(data_dict)]])
        return True
    except:
        return False

st.set_page_config(page_title="Dashboard Market Gamer", layout="wide")
st.title("🎮 Dashboard de Ventas - Market Gamer")

COLORES = ["#00C49F", "#009EE3", "#FFD700", "#FF5733", "#AA00FF", "#FF69B4"]

def fmt(n):
    try:
        return f"${float(n):,.0f}".replace(",", ".")
    except:
        return "-"

def fmt_pct(n):
    return f"{n:.2f}%"

# ── Session state ──────────────────────────────────────────────────────────────
for key in ["df_tn", "df_pagos", "costos_productos", "ordenes_efectivo", "ids_venta_local", "orders_raw"]:
    if key not in st.session_state:
        if key == "costos_productos":
            st.session_state[key] = {}
        elif key in ["ordenes_efectivo", "ids_venta_local"]:
            st.session_state[key] = set()
        elif key == "orders_raw":
            st.session_state[key] = []
        else:
            st.session_state[key] = None

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📅 Período")
    periodo = st.radio("Seleccionar período", ["Este mes", "Mes anterior", "Esta semana", "Personalizado"], index=0)
    hoy = date.today()
    if periodo == "Este mes":
        fecha_desde = hoy.replace(day=1); fecha_hasta = hoy
    elif periodo == "Mes anterior":
        primer_dia = hoy.replace(day=1); fecha_hasta = primer_dia - timedelta(days=1); fecha_desde = fecha_hasta.replace(day=1)
    elif periodo == "Esta semana":
        fecha_desde = hoy - timedelta(days=hoy.weekday()); fecha_hasta = hoy
    else:
        fecha_desde = st.date_input("Desde", value=hoy.replace(day=1))
        fecha_hasta = st.date_input("Hasta", value=hoy)
    if periodo != "Personalizado":
        st.info(f"📆 {fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')}")
    buscar = st.button("🔍 Buscar", use_container_width=True)

# ── API Tienda Nube ────────────────────────────────────────────────────────────
def get_tn_headers():
    return {
        "Authentication": f"bearer {TN_TOKEN}",
        "User-Agent": "MarketGamerDashboard (info@marketgamer.com.ar)"
    }

def get_tn_orders(fecha_desde, fecha_hasta):
    headers = get_tn_headers()
    all_orders = []; seen_ids = set()
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
                        **filtros
                    }
                )
                if r.status_code == 404: break
                if r.status_code == 429:
                    st.warning("Rate limit TN, esperando..."); time.sleep(3); continue
                if r.status_code != 200:
                    st.warning(f"TN respondió {r.status_code}: {r.text[:100]}"); break
                try: data = r.json()
                except: st.warning("TN devolvió respuesta inesperada"); break
                if not data: break
                for o in data:
                    oid = o.get("id")
                    if oid not in seen_ids:
                        seen_ids.add(oid); all_orders.append(o)
                if len(data) < 50: break
                page += 1
    return all_orders

def get_tn_pagos(fecha_desde, fecha_hasta):
    """Trae transacciones de Pago Nube del período"""
    headers = get_tn_headers()
    all_pagos = []; seen_ids = set()
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
                }
            )
            if r.status_code in [404, 422]: break
            if r.status_code == 429:
                st.warning("Rate limit Pago Nube, esperando..."); time.sleep(3); continue
            if r.status_code != 200: break
            try: data = r.json()
            except: break
            if not data: break
            for p in data:
                pid = p.get("id")
                if pid not in seen_ids:
                    seen_ids.add(pid); all_pagos.append(p)
            if len(data) < 50: break
            page += 1
    return all_pagos

def get_tn_products():
    """Trae todos los productos con stock y variantes"""
    headers = get_tn_headers()
    all_products = []
    page = 1
    while True:
        r = requests.get(
            f"https://api.tiendanube.com/v1/{TN_STORE_ID}/products",
            headers=headers,
            params={"per_page": 50, "page": page}
        )
        if r.status_code != 200: break
        try: data = r.json()
        except: break
        if not data: break
        all_products.extend(data)
        if len(data) < 50: break
        page += 1
    return all_products

# TASAS REALES DE PAGO NUBE calibradas con transacciones reales
# Procesamiento: 3.29% + IVA, factor IVA real = 1.26x
# Verificado: orden #339 $500k 6c -> $118,500 calculado vs $118,503 real
PROC_BASE     = 0.0329
IVA_FACTOR    = 1.2600
PROC_EFECTIVO = PROC_BASE * IVA_FACTOR  # 4.1454%

CUOTAS_BASE = {
    1:  0.0,
    2:  0.0606,
    3:  0.0798,
    6:  0.1552,
    12: 0.3104,
    18: 0.4346,
    24: 0.5432,
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


def procesar_orders(orders):
    filas = []
    for o in orders:
        prods = []
        costo_productos = 0.0
        for p in o.get("products", []):
            n = p.get("name", "")
            nombre = n if isinstance(n, str) else (n.get("es", "") or next(iter(n.values()), "")) if isinstance(n, dict) else ""
            prods.append(nombre)
            qty = int(p.get("quantity", 1) or 1)
            cost = float(p.get("cost", 0) or 0)
            costo_productos += cost * qty
        productos = " / ".join(prods)
        cantidad = sum(p.get("quantity", 1) for p in o.get("products", []))
        pd_raw = o.get("payment_details", {})
        gateway = str(o.get("gateway", "")).lower()
        metodo = gateway
        cuotas = 1
        tarjeta = ""
        if isinstance(pd_raw, dict):
            metodo = pd_raw.get("method", gateway)
            cuotas = int(pd_raw.get("installments", 1) or 1)
            tarjeta = pd_raw.get("credit_card_company", "") or ""
        if metodo == "credit_card":
            if cuotas == 1:
                label_medio = "Credito contado"
            else:
                label_medio = f"Credito {cuotas} cuotas"
        elif metodo == "debit_card":
            label_medio = "Debito"
        elif any(x in str(metodo).lower() for x in ["transfer", "wire"]):
            label_medio = "Transferencia"
        elif "account_money" in str(metodo).lower():
            label_medio = "Dinero en cuenta"
        else:
            label_medio = str(metodo).replace("_", " ").title() if metodo else str(gateway)
        try: fecha = pd.to_datetime(o.get("created_at", "")).strftime("%Y-%m-%d")
        except: fecha = ""
        total = float(o.get("total", 0))
        descuento = float(o.get("discount", 0) or 0)
        costo_envio_dueno = float(o.get("shipping_cost_owner", 0) or 0)
        tasa = tasa_pago_nube(metodo, cuotas)
        comision_pn = round(total * tasa, 2)
        neto = round(total - comision_pn, 2)
        pct_costo = round(tasa * 100, 2)
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
            "Costo PN (%)": pct_costo,
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
        try: fecha = pd.to_datetime(p.get("created_at", "")).strftime("%Y-%m-%d")
        except: fecha = ""
        monto = float(p.get("amount", 0) or 0)
        filas.append({
            "ID": str(p.get("id", "")),
            "Fecha": fecha,
            "Estado": p.get("status", ""),
            "Método": p.get("payment_method", ""),
            "Cuotas": p.get("installments", 1),
            "Monto ($)": monto,
            "Orden TN": str(p.get("order_id", "")),
        })
    return pd.DataFrame(filas) if filas else pd.DataFrame()

# ── Búsqueda ───────────────────────────────────────────────────────────────────
if buscar:
    orders = get_tn_orders(fecha_desde, fecha_hasta)
    if orders:
        # Filtrar estrictamente por fecha (la API puede devolver órdenes del día siguiente)
        orders_filtrados = []
        for o in orders:
            try:
                fecha_orden = pd.to_datetime(o.get("created_at","")).tz_localize(None) if pd.to_datetime(o.get("created_at","")).tzinfo is None else pd.to_datetime(o.get("created_at","")).tz_convert(None)
                fecha_ord_date = fecha_orden.date()
                if fecha_desde <= fecha_ord_date <= fecha_hasta:
                    orders_filtrados.append(o)
            except:
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
    if pagos:
        st.session_state.df_pagos = procesar_pagos_pn(pagos)
    else:
        st.session_state.df_pagos = pd.DataFrame()

    st.session_state.ordenes_efectivo = set()
    st.session_state.ids_venta_local = set()

# ── Tabs ───────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_dolar_blue():
    try:
        r = requests.get("https://api.bluelytics.com.ar/v2/latest", timeout=5)
        if r.status_code == 200:
            data = r.json()
            return float(data["blue"]["value_sell"])
    except:
        pass
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=5)
        if r.status_code == 200:
            return float(r.json().get("venta", 0))
    except:
        pass
    return None

# ── FOB defaults por producto (promedio ponderado histórico de compras) ────────
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

if st.session_state.df_tn is not None:
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "📊 Dashboard",
        "🔍 Detalle y ajustes",
        "💸 Transferencias",
        "💚 Salud Financiera",
        "📦 Stock",
        "📬 Tracking WhatsApp",
        "🔥 Velocidad de ventas",
        "🏗️ Gastos fijos",
        "💻 Costos de consolas"
    ])
    df_tn = st.session_state.df_tn.copy()
    df_pagos = st.session_state.df_pagos.copy() if st.session_state.df_pagos is not None else pd.DataFrame()

    # ── TAB 1: DASHBOARD ──────────────────────────────────────────────────────
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

            col_a, col_b = st.columns(2)
            with col_a:
                # Ventas por día
                fig_dia = px.bar(
                    df_tn.groupby("Fecha")["Total ($)"].sum().reset_index(),
                    x="Fecha", y="Total ($)", title="Ventas por día",
                    color_discrete_sequence=["#009EE3"]
                )
                fig_dia.update_layout(yaxis_tickformat="$,.0f")
                st.plotly_chart(fig_dia, use_container_width=True)
            with col_b:
                top_prods = {}
                for _, row in df_tn.iterrows():
                    for p in str(row.get("Productos", "")).split(" / "):
                        p = p.strip()
                        if p:
                            top_prods[p] = top_prods.get(p, 0) + row.get("Cantidad", 1)
                if top_prods:
                    df_tp = pd.DataFrame(list(top_prods.items()), columns=["Producto", "Unidades"])
                    df_tp = df_tp.sort_values("Unidades", ascending=False).head(10)
                    fig_tp = px.bar(df_tp, x="Unidades", y="Producto", orientation="h",
                        title="Top 10 productos más vendidos", color_discrete_sequence=["#00C49F"])
                    fig_tp.update_layout(yaxis={"categoryorder": "total ascending"})
                    st.plotly_chart(fig_tp, use_container_width=True)

            # Distribución de comisiones por medio de pago
            st.divider()
            st.subheader("💳 Distribución de costos Pago Nube por medio de pago")
            comis_medio = df_tn.groupby("Medio de Pago").agg(
                Ordenes=("Orden", "count"),
                Facturacion=("Total ($)", "sum"),
                Comision=("Comision PN ($)", "sum"),
            ).reset_index().sort_values("Comision", ascending=False)
            comis_medio["Costo %"] = (comis_medio["Comision"] / comis_medio["Facturacion"] * 100).round(2)

            col_pie, col_bar = st.columns(2)
            with col_pie:
                fig_pie_com = px.pie(
                    comis_medio, names="Medio de Pago", values="Comision", hole=0.45,
                    title="Comisiones por medio de pago ($)",
                    color_discrete_sequence=COLORES
                )
                fig_pie_com.update_traces(
                    texttemplate="<b>%{label}</b><br>$%{value:,.0f}<br>%{percent}",
                    textposition="outside"
                )
                fig_pie_com.update_layout(showlegend=False)
                st.plotly_chart(fig_pie_com, use_container_width=True)
            with col_bar:
                fig_bar_com = px.bar(
                    comis_medio, x="Medio de Pago", y="Comision",
                    title="Monto de comisión por medio de pago",
                    color="Costo %",
                    color_continuous_scale=["#00C49F", "#FFD700", "#FF5733"],
                    text="Comision"
                )
                fig_bar_com.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
                fig_bar_com.update_layout(yaxis_tickformat="$,.0f", coloraxis_showscale=False)
                st.plotly_chart(fig_bar_com, use_container_width=True)

            # Tabla resumen
            comis_medio_fmt = comis_medio.copy()
            comis_medio_fmt["Facturacion"] = comis_medio_fmt["Facturacion"].apply(fmt)
            comis_medio_fmt["Comision"] = comis_medio_fmt["Comision"].apply(fmt)
            comis_medio_fmt["Costo %"] = comis_medio_fmt["Costo %"].apply(fmt_pct)
            comis_medio_fmt.columns = ["Medio de Pago", "Órdenes", "Facturación", "Comisión PN", "Costo %"]
            st.dataframe(comis_medio_fmt, use_container_width=True, hide_index=True)



    # ── TAB 2: DETALLE ────────────────────────────────────────────────────────
    with tab2:
        st.subheader("🛍️ Detalle de órdenes — Tienda Nube")
        if df_tn.empty:
            st.info("No hay órdenes en este período.")
        else:
            cols_tn = ["Orden", "Fecha", "Cliente", "Medio de Pago", "Cuotas", "Total ($)",
                       "Descuento ($)", "Envio costo ($)", "Comision PN ($)",
                       "Costo PN (%)", "Neto cobrado ($)", "Costo Productos ($)",
                       "Margen ($)", "Margen (%)", "Estado Envio", "Productos", "Cantidad", "Canal"]
            cols_tn = [c for c in cols_tn if c in df_tn.columns]
            st.dataframe(
                df_tn[cols_tn].style.format({
                    "Total ($)": "${:,.0f}", "Descuento ($)": "${:,.0f}",
                    "Envio costo ($)": "${:,.0f}", "Comision PN ($)": "${:,.0f}",
                    "Costo PN (%)": "{:.2f}%", "Neto cobrado ($)": "${:,.0f}",
                    "Costo Productos ($)": "${:,.0f}", "Margen ($)": "${:,.0f}", "Margen (%)": "{:.2f}%",
                }),
                use_container_width=True, hide_index=True
            )
            st.download_button("⬇️ Descargar CSV órdenes TN",
                df_tn[cols_tn].to_csv(index=False).encode("utf-8"), "ordenes_tn.csv", "text/csv")

        st.divider()
        st.subheader("📊 Resumen por medio de pago")
        if not df_tn.empty:
            res = df_tn.groupby("Medio de Pago").agg(
                Cantidad=("Orden", "count"),
                Bruto=("Total ($)", "sum"),
                Comision=("Comision PN ($)", "sum"),
                Neto=("Neto cobrado ($)", "sum"),
                CostoProds=("Costo Productos ($)", "sum"),
                Margen=("Margen ($)", "sum"),
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
                df_pagos.style.format({"Monto ($)": "${:,.0f}"}),
                use_container_width=True, hide_index=True
            )
            st.download_button("⬇️ Descargar CSV Pago Nube",
                df_pagos.to_csv(index=False).encode("utf-8"), "pagos_pagonube.csv", "text/csv")

    # ── TAB 3: TRANSFERENCIAS Y EFECTIVO ─────────────────────────────────────
    with tab3:
        st.subheader("💸 Órdenes por transferencia y efectivo")
        st.caption("Pago Nube ya está integrado en TN — aquí se muestran los pagos fuera de la pasarela.")
        if df_tn.empty:
            st.info("Buscá primero para cargar los datos.")
        else:
            filas_conc = []
            for _, row in df_tn.iterrows():
                orden = str(row["Orden"])
                total = row["Total ($)"]
                medio = str(row.get("Medio de Pago", "")).lower()

                # Buscar pago en Pago Nube
                pago_match = None
                if not df_pagos.empty:
                    match = df_pagos[df_pagos["Orden TN"] == orden]
                    if not match.empty:
                        pago_match = match.iloc[0]

                if orden in st.session_state.ordenes_efectivo:
                    estado = "💵 Efectivo"
                elif pago_match is not None:
                    if pago_match["Estado"] == "paid":
                        dif = round(total - pago_match["Monto ($)"], 0)
                        estado = "✅ Cobrado en PN"
                    else:
                        estado = f"⚠️ Estado: {pago_match['Estado']}"
                elif "transfer" in medio or "efectivo" in medio:
                    estado = "❓ Sin verificar"
                else:
                    estado = "❓ Sin verificar"

                filas_conc.append({
                    "Orden TN": orden,
                    "Fecha": row["Fecha"],
                    "Cliente": row["Cliente"],
                    "Productos": row["Productos"],
                    "Medio de Pago": row["Medio de Pago"],
                    "Total TN ($)": total,
                    "Estado": estado,
                    "ID Pago PN": pago_match["ID"] if pago_match is not None else "-",
                })

            df_conc = pd.DataFrame(filas_conc)

            total_ord = len(df_conc)
            cobrados = len(df_conc[df_conc["Estado"].str.startswith("✅")])
            efectivo = len(df_conc[df_conc["Estado"].str.startswith("💵")])
            sin_ver = len(df_conc[df_conc["Estado"].str.contains("❓|⚠️")])

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total órdenes", total_ord)
            c2.metric("✅ Verificadas en PN", cobrados)
            c3.metric("💵 Efectivo", efectivo)
            c4.metric("❓ Sin verificar", sin_ver)
            st.divider()

            sin_verif = df_conc[df_conc["Estado"].str.contains("❓|⚠️")]
            if not sin_verif.empty:
                with st.expander("💵 Marcar órdenes como Efectivo", expanded=False):
                    for _, row in sin_verif.drop_duplicates(subset=["Orden TN"]).iterrows():
                        orden = row["Orden TN"]
                        es_ef = st.checkbox(
                            f"📅 {row['Fecha']}  |  👤 {row['Cliente']}  |  💰 {fmt(row['Total TN ($)'])}  |  #{orden}",
                            value=orden in st.session_state.ordenes_efectivo,
                            key=f"efec_{orden}"
                        )
                        if es_ef: st.session_state.ordenes_efectivo.add(orden)
                        else: st.session_state.ordenes_efectivo.discard(orden)
                    # Actualizar estados
                    df_conc["Estado"] = df_conc.apply(
                        lambda r: "💵 Efectivo" if r["Orden TN"] in st.session_state.ordenes_efectivo else r["Estado"], axis=1
                    )

            estados = df_conc["Estado"].unique().tolist()
            filtro = st.multiselect("Filtrar por estado", estados, default=estados)
            df_conc_f = df_conc[df_conc["Estado"].isin(filtro)]

            def color_e(val):
                if "✅" in str(val): return "background-color: #1a3a1a"
                if "💵" in str(val): return "background-color: #1a2a3a"
                if "❓" in str(val) or "⚠️" in str(val): return "background-color: #3a2a1a"
                return ""

            st.dataframe(
                df_conc_f.style.format({"Total TN ($)": "${:,.0f}"}).applymap(color_e, subset=["Estado"]),
                use_container_width=True, hide_index=True
            )
            st.download_button("⬇️ Descargar conciliación",
                df_conc_f.to_csv(index=False).encode("utf-8"), "conciliacion.csv", "text/csv")

            # Pagos PN sin orden
            if not df_pagos.empty:
                st.divider()
                st.subheader("🔍 Pagos de Pago Nube sin orden en TN")
                ordenes_tn_set = set(df_tn["Orden"].astype(str))
                pagos_sin_orden = df_pagos[~df_pagos["Orden TN"].isin(ordenes_tn_set)]
                if pagos_sin_orden.empty:
                    st.success("✅ Todos los pagos de PN están cruzados con órdenes de TN.")
                else:
                    st.warning(f"{len(pagos_sin_orden)} pago(s) de PN sin orden en TN.")
                    st.dataframe(pagos_sin_orden.style.format({"Monto ($)": "${:,.0f}"}),
                        use_container_width=True, hide_index=True)

    # ── TAB 4: SALUD FINANCIERA ───────────────────────────────────────────────
    with tab4:
        st.subheader("💚 Salud Financiera del Período")

        dolar_blue = get_dolar_blue()
        with st.expander("⚙️ Configuración", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                dolar_default = int(dolar_blue) if dolar_blue else 1200
                dolar_label = f"💵 Dólar blue venta (auto: ${dolar_default:,.0f})" if dolar_blue else "💵 Tipo de cambio (ARS/USD)"
                tipo_cambio = st.number_input(dolar_label, value=dolar_default, step=10)
                if dolar_blue:
                    st.caption(f"🔄 Actualizado automáticamente · ${dolar_blue:,.0f} ARS")
            with col2:
                pct_iva = st.slider("🧾 IVA efectivo (%)", min_value=0.0, max_value=21.0, value=10.5, step=0.5,
                    help="Configurá el IVA según tu régimen fiscal")
            with col3:
                pauta_manual = st.number_input("📣 Pauta publicitaria del período (ARS)", value=0, step=50_000)

        with st.expander("💳 Tasas de Pago Nube por cuotas (ajustables)", expanded=False):
            st.caption("Calibradas con tu contrato real. Verificado: 6 cuotas = 23.70% (orden #339 $500k → neto $381.497)")
            st.info("Procesamiento: 3.29% + IVA (retiro 14 dias) | Transferencia: 0.99% + IVA | Factor IVA: 1.26x")
            tc1, tc2, tc3, tc4, tc5, tc6 = st.columns(6)
            tasa_1c  = tc1.number_input("1 cuota (%)",  value=4.15, step=0.01, key="t1") / 100
            tasa_2c  = tc2.number_input("2 cuotas (%)", value=11.78, step=0.01, key="t2") / 100
            tasa_3c  = tc3.number_input("3 cuotas (%)", value=14.20, step=0.01, key="t3") / 100
            tasa_6c  = tc4.number_input("6 cuotas (%)", value=23.70, step=0.01, key="t6") / 100
            tasa_12c = tc5.number_input("12 cuotas (%)",value=43.24, step=0.01, key="t12") / 100
            tasa_deb = tc6.number_input("Deb/Trans (%)", value=4.15, step=0.01, key="tdeb") / 100
            tasas_custom = {1: tasa_1c, 2: tasa_2c, 3: tasa_3c, 6: tasa_6c,
                           9: (tasa_6c+tasa_12c)/2, 12: tasa_12c,
                           18: tasa_12c*1.15, 24: tasa_12c*1.30, "debit": tasa_deb}

        st.divider()
        st.subheader("💰 Resumen financiero del período")

        if df_tn.empty:
            st.info("Buscá primero para ver los datos financieros.")
        else:
            # Recalcular comisiones con tasas custom del usuario
            def comision_custom(row):
                metodo = str(row.get("Medio de Pago","")).lower()
                cuotas = int(row.get("Cuotas", 1) or 1)
                total  = float(row.get("Total ($)", 0))
                if "debit" in metodo or "debito" in metodo:
                    tasa = tasas_custom.get("debit", 0.0199)
                else:
                    opciones = [k for k in tasas_custom.keys() if isinstance(k, int)]
                    tasa_key = min(opciones, key=lambda x: abs(x - cuotas))
                    tasa = tasas_custom.get(tasa_key, 0.0414)
                return round(total * tasa, 2)

            df_calc = df_tn.copy()
            df_calc["Comision PN ($)"] = df_calc.apply(comision_custom, axis=1)
            df_calc["Neto cobrado ($)"] = df_calc["Total ($)"] - df_calc["Comision PN ($)"]
            df_calc["Margen ($)"] = df_calc["Neto cobrado ($)"] - df_calc["Costo Productos ($)"] - df_calc["Envio costo ($)"]

            # Totales
            facturacion_bruta   = df_calc["Total ($)"].sum()
            comisiones_pn       = df_calc["Comision PN ($)"].sum()
            neto_cobrado        = df_calc["Neto cobrado ($)"].sum()
            costo_productos     = df_calc["Costo Productos ($)"].sum()
            costo_envios        = df_calc["Envio costo ($)"].sum()
            costo_iva           = facturacion_bruta * (pct_iva / 100)
            margen_bruto        = df_calc["Margen ($)"].sum()
            resultado_final     = margen_bruto - costo_iva - pauta_manual

            # Métricas principales
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Facturacion bruta",   fmt(facturacion_bruta))
            k2.metric("Comisiones PN",       fmt(comisiones_pn),   delta=f"-{fmt(comisiones_pn)}",   delta_color="inverse")
            k3.metric("Neto cobrado",         fmt(neto_cobrado))
            k4.metric("Costo productos",     fmt(costo_productos), delta=f"-{fmt(costo_productos)}", delta_color="inverse")
            k5.metric("Costo envios",         fmt(costo_envios),    delta=f"-{fmt(costo_envios)}",    delta_color="inverse")

            st.divider()
            g1, g2, g3 = st.columns(3)
            g1.metric("Margen bruto",        fmt(margen_bruto))
            g2.metric(f"IVA ({pct_iva:.1f}%)", fmt(costo_iva),    delta=f"-{fmt(costo_iva)}",        delta_color="inverse")
            g3.metric("Pauta publicitaria",  fmt(pauta_manual),    delta=f"-{fmt(pauta_manual)}",     delta_color="inverse")

            st.divider()
            st.metric(f"{'🟢' if resultado_final >= 0 else '🔴'} RESULTADO FINAL DEL PERÍODO", fmt(resultado_final))
            if resultado_final >= 0:
                st.success(f"✅ Resultado positivo: {fmt(resultado_final)}")
            else:
                st.error(f"⚠️ Resultado negativo: -{fmt(abs(resultado_final))}")

            # Detalle por orden con margen
            st.divider()
            st.subheader("📋 Detalle por orden con margen real")
            cols_fin = ["Orden","Fecha","Cliente","Medio de Pago","Cuotas","Total ($)",
                        "Comision PN ($)","Neto cobrado ($)","Costo Productos ($)","Envio costo ($)","Margen ($)","Margen (%)"]
            cols_fin = [c for c in cols_fin if c in df_calc.columns]
            st.dataframe(
                df_calc[cols_fin].style.format({
                    "Total ($)": "${:,.0f}", "Comision PN ($)": "${:,.0f}",
                    "Neto cobrado ($)": "${:,.0f}", "Costo Productos ($)": "${:,.0f}",
                    "Envio costo ($)": "${:,.0f}", "Margen ($)": "${:,.0f}", "Margen (%)": "{:.1f}%",
                }),
                use_container_width=True, hide_index=True
            )

            # Cascada
            st.divider()
            st.subheader("📊 Cascada de resultados")
            wf = pd.DataFrame({
                "Concepto": ["Facturacion bruta","Comisiones PN","Costo productos","Costo envios",f"IVA ({pct_iva:.1f}%)","Pauta","Resultado final"],
                "Monto":    [facturacion_bruta, -comisiones_pn, -costo_productos, -costo_envios, -costo_iva, -pauta_manual, resultado_final],
                "Color":    ["#00C49F","#FF9900","#FF5733","#FF5733","#FF5733","#FF9900","#009EE3" if resultado_final >= 0 else "#FF0000"],
            })
            fig_wf = px.bar(wf, x="Concepto", y="Monto", color="Concepto",
                color_discrete_sequence=wf["Color"].tolist(), title="Cascada financiera del periodo")
            fig_wf.update_layout(showlegend=False, yaxis_tickformat="$,.0f")
            fig_wf.update_traces(texttemplate="%{y:$,.0f}", textposition="outside")
            st.plotly_chart(fig_wf, use_container_width=True)

    # ── TAB 5: STOCK ──────────────────────────────────────────────────────────
    with tab5:
        st.subheader("📦 Stock — Tienda Nube")

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
                        sku = v.get("sku", "")
                        vals = v.get("values", [])
                        variante = " / ".join([
                            (val.get("es", "") or next(iter(val.values()), "")) if isinstance(val, dict) else str(val)
                            for val in vals
                        ]) if vals else "—"
                        precio = float(v.get("price", 0) or 0)
                        stock_rows.append({
                            "Producto": nombre,
                            "Variante": variante,
                            "SKU": sku,
                            "Stock": stock if stock is not None else "Sin límite",
                            "Precio ($)": precio,
                        })
                st.session_state.stock_tn = pd.DataFrame(stock_rows)
                st.success(f"✅ {len(stock_rows)} variantes cargadas")
            else:
                st.warning("No se pudieron cargar productos.")

        if "stock_tn" in st.session_state and st.session_state.stock_tn is not None:
            df_stock = st.session_state.stock_tn

            # Filtros
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                buscar_prod = st.text_input("🔍 Buscar producto", "")
            with col_f2:
                mostrar_sin_stock = st.checkbox("Mostrar solo sin stock o stock bajo", value=False)

            df_stock_f = df_stock.copy()
            if buscar_prod:
                df_stock_f = df_stock_f[df_stock_f["Producto"].str.contains(buscar_prod, case=False, na=False)]
            if mostrar_sin_stock:
                df_stock_f = df_stock_f[
                    df_stock_f["Stock"].apply(lambda x: isinstance(x, (int, float)) and x <= 3)
                ]

            st.dataframe(
                df_stock_f.style.format({"Precio ($)": "${:,.0f}"}),
                use_container_width=True, hide_index=True
            )

            # Alertas de stock bajo
            st.divider()
            st.subheader("⚠️ Alertas de stock bajo")
            umbral = st.slider("Umbral de alerta (unidades)", min_value=1, max_value=20, value=5)
            alertas = df_stock[
                df_stock["Stock"].apply(lambda x: isinstance(x, (int, float)) and x <= umbral)
            ]
            if alertas.empty:
                st.success(f"✅ Todos los productos tienen más de {umbral} unidades en stock.")
            else:
                st.warning(f"⚠️ {len(alertas)} variante(s) con stock ≤ {umbral}")
                st.dataframe(alertas.style.format({"Precio ($)": "${:,.0f}"}),
                    use_container_width=True, hide_index=True)

            # Resumen
            st.divider()
            st.subheader("📊 Resumen de stock")
            r1, r2, r3 = st.columns(3)
            stock_numerico = df_stock[df_stock["Stock"].apply(lambda x: isinstance(x, (int, float)))]
            r1.metric("Total productos", df_stock["Producto"].nunique())
            r2.metric("Total variantes", len(df_stock))
            r3.metric("Total unidades en stock", int(stock_numerico["Stock"].sum()))

            st.download_button("⬇️ Descargar stock",
                df_stock.to_csv(index=False).encode("utf-8"), "stock_marketgamer.csv", "text/csv")
        else:
            st.info("👆 Hacé clic en 'Cargar stock desde Tienda Nube' para ver el inventario.")

    # ── TAB 6: WHATSAPP TRACKING ──────────────────────────────────────────────
    with tab6:
        st.subheader("📬 Enviar código de seguimiento por WhatsApp")
        st.caption("Se abre WhatsApp con el mensaje listo. Solo hacé clic en Enviar.")

        # Plantilla de mensaje configurable
        with st.expander("✏️ Personalizar mensaje", expanded=False):
            plantilla = st.text_area(
                "Plantilla del mensaje",
                value="""Hola {nombre}! 👋
Tu pedido de Market Gamer ya fue despachado 🎮📦

Podés rastrear tu envío con el siguiente código:
*{tracking}*

🔗 Seguimiento Correo Argentino:
https://www.correoargentino.com.ar/formularios/e-commerce?id={tracking}

Cualquier consulta estamos a disposición 😊""",
                height=200,
                help="Usá {nombre} para el nombre del cliente y {tracking} para el código de seguimiento"
            )

        st.divider()

        if df_tn.empty:
            st.info("Buscá primero para ver las órdenes.")
        else:
            # Filtrar órdenes con tracking disponible
            df_track = df_tn.copy()

            # Necesitamos el tracking y teléfono — vienen de las órdenes raw
            # Reconstruir desde session state con datos adicionales
            ordenes_raw = st.session_state.get("orders_raw", [])

            if not ordenes_raw:
                st.warning("Volvé a hacer la búsqueda para cargar los datos de tracking.")
            else:
                filas_wpp = []
                for o in ordenes_raw:
                    tracking = o.get("shipping_tracking_number") or ""
                    tracking_url = o.get("shipping_tracking_url") or ""
                    telefono = o.get("contact_phone") or ""
                    nombre = o.get("contact_name") or ""
                    numero = o.get("number")
                    productos_list = []
                    for p in o.get("products", []):
                        n = p.get("name", "")
                        nombre_prod = n if isinstance(n, str) else (n.get("es", "") if isinstance(n, dict) else "")
                        productos_list.append(nombre_prod)
                    productos_str = " / ".join(productos_list)
                    estado_envio = o.get("shipping_status", "")

                    filas_wpp.append({
                        "Orden": numero,
                        "Cliente": nombre,
                        "Telefono": telefono,
                        "Productos": productos_str,
                        "Estado envio": estado_envio,
                        "Tracking": tracking,
                        "_tracking_url": tracking_url,
                    })

                df_wpp = pd.DataFrame(filas_wpp)

                # Métricas
                con_tracking = df_wpp[df_wpp["Tracking"].str.len() > 0]
                sin_tracking = df_wpp[df_wpp["Tracking"].str.len() == 0]

                m1, m2, m3 = st.columns(3)
                m1.metric("Total órdenes", len(df_wpp))
                m2.metric("✅ Con tracking", len(con_tracking))
                m3.metric("⏳ Sin tracking aún", len(sin_tracking))

                st.divider()

                # Filtro
                mostrar = st.radio("Mostrar", ["Con tracking", "Sin tracking", "Todas"], horizontal=True)
                if mostrar == "Con tracking":
                    df_mostrar = con_tracking
                elif mostrar == "Sin tracking":
                    df_mostrar = sin_tracking
                else:
                    df_mostrar = df_wpp

                if df_mostrar.empty:
                    st.info("No hay órdenes en esta categoría.")
                else:
                    st.markdown(f"**{len(df_mostrar)} órdenes**")

                    for _, row in df_mostrar.iterrows():
                        tracking = str(row["Tracking"]).strip()
                        telefono = str(row["Telefono"]).strip()
                        nombre_cliente = str(row["Cliente"]).strip()

                        with st.container():
                            col_info, col_btn = st.columns([4, 1])

                            with col_info:
                                tiene_tracking = len(tracking) > 0
                                estado_icon = "✅" if tiene_tracking else "⏳"
                                st.markdown(
                                    f"{estado_icon} **#{row['Orden']}** — {nombre_cliente} "
                                    f"| 📱 `{telefono}` "
                                    f"| 📦 {row['Productos']}"
                                )
                                if tiene_tracking:
                                    st.caption(f"Tracking: `{tracking}`")
                                else:
                                    st.caption("Sin código de seguimiento todavía")

                            with col_btn:
                                if tiene_tracking and telefono:
                                    # Limpiar teléfono para wa.me (solo números)
                                    tel_limpio = "".join(filter(str.isdigit, telefono))
                                    # Argentina: si empieza con 54 y tiene 9 después, está bien
                                    # Si empieza con 0, sacar el 0 y agregar 54
                                    if tel_limpio.startswith("0"):
                                        tel_limpio = "54" + tel_limpio[1:]
                                    elif not tel_limpio.startswith("54"):
                                        tel_limpio = "54" + tel_limpio

                                    # Armar mensaje desde plantilla
                                    mensaje = plantilla.replace("{nombre}", nombre_cliente.split()[0] if nombre_cliente else "")
                                    mensaje = mensaje.replace("{tracking}", tracking)

                                    # Encodear para URL
                                    import urllib.parse
                                    msg_encoded = urllib.parse.quote(mensaje)
                                    wpp_url = f"https://wa.me/{tel_limpio}?text={msg_encoded}"

                                    st.link_button("📲 Enviar WPP", wpp_url, use_container_width=True)
                                elif not telefono:
                                    st.caption("Sin teléfono")
                                else:
                                    st.button("⏳ Sin tracking", disabled=True, key=f"dis_{row['Orden']}", use_container_width=True)

                            st.divider()


    # ── TAB 7: VELOCIDAD DE VENTAS / RESTOCK ─────────────────────────────────
    with tab7:
        st.subheader("🔥 Velocidad de ventas y planificación de restock")

        if df_tn.empty:
            st.info("Buscá primero para ver los datos de ventas.")
        else:
            dias_periodo = max((fecha_hasta - fecha_desde).days + 1, 1)

            # ── Construir tabla de ventas por producto ──────────────────────
            ventas_por_prod = {}
            for _, row in df_tn.iterrows():
                for p in str(row.get("Productos", "")).split(" / "):
                    p = p.strip()
                    if not p:
                        continue
                    if p not in ventas_por_prod:
                        ventas_por_prod[p] = {"unidades": 0, "revenue": 0.0, "ordenes": 0}
                    qty = int(row.get("Cantidad", 1) or 1)
                    # Si hay múltiples productos en la orden, distribuir revenue
                    n_prods = len([x for x in str(row.get("Productos","")).split(" / ") if x.strip()])
                    ventas_por_prod[p]["unidades"] += qty
                    ventas_por_prod[p]["revenue"]  += row.get("Total ($)", 0) / max(n_prods, 1)
                    ventas_por_prod[p]["ordenes"]  += 1

            if not ventas_por_prod:
                st.info("No hay datos de productos para el período.")
            else:
                # Cruzar con stock de TN si está cargado
                stock_map = {}
                if "stock_tn" in st.session_state and st.session_state.stock_tn is not None:
                    for _, srow in st.session_state.stock_tn.iterrows():
                        prod_nombre = srow["Producto"]
                        stock_val = srow["Stock"]
                        if isinstance(stock_val, (int, float)):
                            stock_map[prod_nombre] = stock_map.get(prod_nombre, 0) + int(stock_val)

                # ── Configuración ──────────────────────────────────────────
                with st.expander("⚙️ Configuración de alertas", expanded=False):
                    ca, cb = st.columns(2)
                    dias_alerta = ca.slider("⚠️ Alertar si queda stock para menos de X días", 1, 60, 14)
                    dias_restock = cb.slider("📦 Días de lead time para restock", 1, 45, 7,
                        help="Cuántos días tarda en llegar tu mercadería después de pedirla")

                st.divider()

                # ── Construir DataFrame ────────────────────────────────────
                rows = []
                for prod, data in ventas_por_prod.items():
                    unidades    = data["unidades"]
                    revenue     = data["revenue"]
                    vel_dia     = round(unidades / dias_periodo, 3)   # unidades/día
                    vel_semana  = round(vel_dia * 7, 2)
                    vel_mes     = round(vel_dia * 30, 1)
                    stock_actual = stock_map.get(prod, None)

                    if stock_actual is not None and vel_dia > 0:
                        dias_restantes = round(stock_actual / vel_dia, 0)
                        fecha_agotamiento = pd.Timestamp.now() + pd.Timedelta(days=dias_restantes)
                        fecha_agot_str = fecha_agotamiento.strftime("%d/%m/%Y")
                        necesita_restock = dias_restantes <= (dias_alerta + dias_restock)
                        restock_units = max(0, round(vel_dia * 30 - stock_actual + vel_dia * dias_restock))
                    elif stock_actual is not None and vel_dia == 0:
                        dias_restantes = None
                        fecha_agot_str = "—"
                        necesita_restock = False
                        restock_units = 0
                    else:
                        dias_restantes = None
                        fecha_agot_str = "Sin stock cargado"
                        necesita_restock = False
                        restock_units = 0

                    # Score de urgencia (0-100): combina velocidad + proximidad agotamiento
                    if dias_restantes is not None and vel_dia > 0:
                        urgencia = min(100, round((vel_dia * 10) + max(0, (30 - dias_restantes) * 2)))
                    else:
                        urgencia = round(vel_dia * 10)

                    rows.append({
                        "Producto":           prod,
                        "Unidades vendidas":  unidades,
                        "Vel. diaria":        vel_dia,
                        "Vel. semanal":       vel_semana,
                        "Vel. mensual":       vel_mes,
                        "Revenue ($)":        round(revenue),
                        "Stock actual":       stock_actual if stock_actual is not None else "—",
                        "Días restantes":     int(dias_restantes) if dias_restantes is not None else "—",
                        "Se agota":           fecha_agot_str,
                        "Restock sugerido":   restock_units if restock_units > 0 else "—",
                        "Urgencia":           urgencia,
                        "_necesita_restock":  necesita_restock,
                    })

                df_vel = pd.DataFrame(rows).sort_values("Urgencia", ascending=False)

                # ── KPIs rápidos ───────────────────────────────────────────
                criticos = df_vel[df_vel["_necesita_restock"] == True]
                v1, v2, v3, v4 = st.columns(4)
                v1.metric("Productos analizados", len(df_vel))
                v2.metric("🔴 Críticos (restock urgente)", len(criticos))
                v3.metric("Período analizado", f"{dias_periodo} días")
                v4.metric("Vel. media del catálogo", f"{df_vel['Vel. diaria'].mean():.2f} u/día")

                # ── Alertas críticas ───────────────────────────────────────
                if not criticos.empty:
                    st.divider()
                    st.error(f"⚠️ {len(criticos)} producto(s) necesitan restock pronto")
                    for _, crow in criticos.iterrows():
                        dias_r = crow["Días restantes"]
                        dias_txt = f"{dias_r} días" if dias_r != "—" else "stock no cargado"
                        st.warning(
                            f"🔴 **{crow['Producto']}** — "
                            f"stock para **{dias_txt}** | "
                            f"vel. {crow['Vel. diaria']} u/día | "
                            f"restock sugerido: **{crow['Restock sugerido']} unidades**"
                        )

                # ── Ranking completo ───────────────────────────────────────
                st.divider()
                st.subheader("📊 Ranking por velocidad de venta")
                st.caption(f"Período: {fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')} ({dias_periodo} días) | Ordenado por urgencia")

                # Gráfico de barras — velocidad diaria
                df_chart = df_vel[["Producto", "Vel. diaria", "Vel. semanal", "Vel. mensual"]].copy()
                df_chart = df_chart.sort_values("Vel. diaria", ascending=True).tail(15)
                fig_vel = px.bar(
                    df_chart, x="Vel. diaria", y="Producto", orientation="h",
                    title="Velocidad de venta diaria (unidades/día)",
                    color="Vel. diaria",
                    color_continuous_scale=["#00C49F", "#FFD700", "#FF5733"],
                    text="Vel. diaria",
                )
                fig_vel.update_layout(showlegend=False, coloraxis_showscale=False, yaxis={"categoryorder":"total ascending"})
                fig_vel.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                st.plotly_chart(fig_vel, use_container_width=True)

                # Tabla completa con colores
                st.subheader("📋 Tabla detallada")
                cols_show = ["Producto", "Unidades vendidas", "Vel. diaria", "Vel. semanal",
                             "Vel. mensual", "Revenue ($)", "Stock actual",
                             "Días restantes", "Se agota", "Restock sugerido", "Urgencia"]

                def color_urgencia(val):
                    try:
                        v = int(val)
                        if v >= 70: return "background-color: #5a1a1a; color: #ff6b6b"
                        if v >= 40: return "background-color: #5a4a1a; color: #ffd700"
                        return "background-color: #1a3a1a; color: #00C49F"
                    except:
                        return ""

                def color_dias(val):
                    try:
                        v = int(val)
                        if v <= 7:  return "background-color: #5a1a1a; color: #ff6b6b"
                        if v <= 14: return "background-color: #5a4a1a; color: #ffd700"
                        return ""
                    except:
                        return ""

                st.dataframe(
                    df_vel[cols_show].style
                        .format({"Revenue ($)": "${:,.0f}", "Vel. diaria": "{:.3f}", "Vel. semanal": "{:.1f}"})
                        .applymap(color_urgencia, subset=["Urgencia"])
                        .applymap(color_dias, subset=["Días restantes"]),
                    use_container_width=True, hide_index=True
                )

                # ── Historial de ventas por producto (gráfico temporal) ────
                st.divider()
                st.subheader("📈 Evolución de ventas en el período")

                prod_sel = st.selectbox(
                    "Seleccioná un producto para ver su evolución",
                    options=df_vel["Producto"].tolist()
                )

                if prod_sel:
                    df_evo = df_tn[df_tn["Productos"].str.contains(prod_sel, na=False, regex=False)].copy()
                    if not df_evo.empty:
                        df_evo_group = df_evo.groupby("Fecha").agg(
                            Unidades=("Cantidad", "sum"),
                            Revenue=("Total ($)", "sum")
                        ).reset_index()
                        df_evo_group["Acumulado"] = df_evo_group["Unidades"].cumsum()

                        fig_evo = px.bar(
                            df_evo_group, x="Fecha", y="Unidades",
                            title=f"Ventas diarias — {prod_sel}",
                            color_discrete_sequence=["#009EE3"]
                        )
                        fig_evo.add_scatter(
                            x=df_evo_group["Fecha"], y=df_evo_group["Acumulado"],
                            mode="lines+markers", name="Acumulado",
                            line=dict(color="#FFD700", width=2), yaxis="y2"
                        )
                        fig_evo.update_layout(
                            yaxis2=dict(overlaying="y", side="right", showgrid=False),
                            legend=dict(orientation="h")
                        )
                        st.plotly_chart(fig_evo, use_container_width=True)

                        total_prod = df_evo_group["Unidades"].sum()
                        vel_prod = round(total_prod / dias_periodo, 2)
                        rev_prod = df_evo_group["Revenue"].sum()
                        ep1, ep2, ep3 = st.columns(3)
                        ep1.metric("Total vendido", f"{int(total_prod)} u")
                        ep2.metric("Velocidad", f"{vel_prod} u/día")
                        ep3.metric("Revenue", fmt(rev_prod))
                    else:
                        st.info("No hay ventas de este producto en el período.")

                st.download_button(
                    "⬇️ Descargar análisis de restock",
                    df_vel[cols_show].to_csv(index=False).encode("utf-8"),
                    "restock_analysis.csv", "text/csv"
                )


    # ── TAB 8: GASTOS FIJOS ───────────────────────────────────────────────────
    with tab8:
        st.subheader("🏗️ Gastos fijos mensuales")
        st.caption("Los datos quedan guardados en Google Sheets automáticamente.")

        # Cargar desde GSheets
        if "gastos_fijos" not in st.session_state:
            saved = gs_read("GastosFijos")
            st.session_state.gastos_fijos = saved if saved else {
                "Bruno": 0, "Coco": 0, "Agencia": 0, "Local": 0,
                "Sueldo Agus": 0, "Sueldo Stella": 0, "Contador": 0,
                "Sueldo Facu": 0, "Otros": 0
            }

        gastos = st.session_state.gastos_fijos.copy()

        st.markdown("**Editá los gastos fijos mensuales (ARS):**")
        col_g1, col_g2 = st.columns(2)
        nuevos_gastos = {}
        items = list(gastos.items())
        mid = (len(items) + 1) // 2

        with col_g1:
            for k, v in items[:mid]:
                nuevos_gastos[k] = st.number_input(k, value=int(v), step=50000, key=f"gf_{k}")
        with col_g2:
            for k, v in items[mid:]:
                nuevos_gastos[k] = st.number_input(k, value=int(v), step=50000, key=f"gf_{k}")

        # Agregar gasto nuevo
        with st.expander("➕ Agregar gasto"):
            ng_col1, ng_col2 = st.columns(2)
            nuevo_nombre = ng_col1.text_input("Nombre del gasto")
            nuevo_monto  = ng_col2.number_input("Monto mensual (ARS)", value=0, step=50000)
            if st.button("Agregar"):
                if nuevo_nombre:
                    nuevos_gastos[nuevo_nombre] = nuevo_monto
                    st.session_state.gastos_fijos = nuevos_gastos
                    gs_write("GastosFijos", nuevos_gastos)
                    st.success(f"✅ '{nuevo_nombre}' agregado")
                    st.rerun()

        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.button("💾 Guardar gastos fijos", use_container_width=True, type="primary"):
            st.session_state.gastos_fijos = nuevos_gastos
            ok = gs_write("GastosFijos", nuevos_gastos)
            if ok:
                st.success("✅ Guardado en Google Sheets")
            else:
                st.warning("⚠️ Guardado solo en sesión (Google Sheets no configurado)")

        st.divider()
        total_gastos = sum(nuevos_gastos.values())
        st.metric("💰 Total gastos fijos mensuales", fmt(total_gastos))

        df_gastos = pd.DataFrame(list(nuevos_gastos.items()), columns=["Concepto", "Monto (ARS)"])
        df_gastos = df_gastos[df_gastos["Monto (ARS)"] > 0].sort_values("Monto (ARS)", ascending=False)
        if not df_gastos.empty:
            fig_g = px.pie(df_gastos, names="Concepto", values="Monto (ARS)", hole=0.4,
                title="Distribución de gastos fijos", color_discrete_sequence=COLORES)
            st.plotly_chart(fig_g, use_container_width=True)

        # Prorrateo por período
        if st.session_state.df_tn is not None and not st.session_state.df_tn.empty:
            st.divider()
            st.subheader("📐 Gastos prorrateados al período analizado")
            dias_periodo = max((fecha_hasta - fecha_desde).days + 1, 1)
            factor = dias_periodo / 30
            gastos_periodo = round(total_gastos * factor)
            st.metric(f"Gastos para {dias_periodo} días ({factor:.2f}x mes)", fmt(gastos_periodo))


    # ── TAB 9: COSTOS DE CONSOLAS ─────────────────────────────────────────────
    with tab9:
        st.subheader("💻 Costos de consolas")
        st.caption("FOB + importación (peso × USD/kg). El peso se trae de Tienda Nube automáticamente.")

        # Cargar desde GSheets
        if "costos_consolas" not in st.session_state:
            saved = gs_read("CostosConsolas")
            # Si hay datos en GSheets los usamos, si no arrancamos con los defaults históricos
            st.session_state.costos_consolas = saved if saved else FOB_DEFAULTS.copy()

        # Dólar blue para mostrar equivalente ARS
        tc_consolas = int(dolar_blue) if dolar_blue else 1200

        # Traer productos y pesos desde TN
        if st.button("🔄 Cargar productos desde Tienda Nube", key="btn_load_consolas"):
            with st.spinner("Cargando productos..."):
                productos_tn = get_tn_products()
            if productos_tn:
                prods_map = {}
                for p in productos_tn:
                    nombre_raw = p.get("name", {})
                    nombre = nombre_raw.get("es", "") if isinstance(nombre_raw, dict) else str(nombre_raw)
                    # Tomar el peso de la primer variante
                    variantes = p.get("variants", [])
                    peso_kg = None
                    for v in variantes:
                        w = v.get("weight")
                        if w:
                            try:
                                peso_kg = float(w)
                                break
                            except:
                                pass
                    if not peso_kg:
                        peso_raw = p.get("weight")
                        try: peso_kg = float(peso_raw) if peso_raw else None
                        except: peso_kg = None
                    prods_map[nombre] = peso_kg
                st.session_state.productos_tn_map = prods_map
                st.success(f"✅ {len(prods_map)} productos cargados")

        productos_map = st.session_state.get("productos_tn_map", {})
        costos = st.session_state.costos_consolas.copy()

        st.divider()

        # Config global de importación
        col_imp1, col_imp2 = st.columns(2)
        costo_kg_usd = col_imp1.number_input(
            "📦 Costo de importación por kg (USD/kg)",
            value=float(costos.get("_costo_kg_usd", 65.0)),
            step=0.5, key="ckg",
            help="Ej: si el flete es $65 USD por kg, ponés 65"
        )
        col_imp2.metric("Dólar blue actual", f"${tc_consolas:,.0f} ARS")
        costos["_costo_kg_usd"] = costo_kg_usd

        st.divider()
        st.markdown("**Costos por consola:**")

        # Lista de productos: los de TN + los que ya teníamos guardados
        all_prods = set(productos_map.keys())
        for k in costos.keys():
            if not k.startswith("_"):
                all_prods.add(k)

        if not all_prods:
            st.info("Cargá los productos desde Tienda Nube con el botón de arriba.")
        else:
            nuevos_costos = {"_costo_kg_usd": costo_kg_usd}
            header = st.columns([3, 1.2, 1.2, 1.2, 1.5])
            header[0].markdown("**Producto**")
            header[1].markdown("**Peso TN (kg)**")
            header[2].markdown("**FOB (USD)**")
            header[3].markdown("**Costo total (USD)**")
            header[4].markdown("**Costo total (ARS)**")

            for prod in sorted(all_prods):
                peso_tn = productos_map.get(prod)
                prod_data = costos.get(prod, {})
                if isinstance(prod_data, dict):
                    fob_saved = prod_data.get("fob_usd", 0.0)
                    peso_saved = prod_data.get("peso_kg", peso_tn or 0.0)
                else:
                    fob_saved = 0.0
                    peso_saved = peso_tn or 0.0

                cols = st.columns([3, 1.2, 1.2, 1.2, 1.5])
                cols[0].write(prod)

                # Peso: mostrar el de TN pero permitir editar si no está
                # Prioridad: TN > FOB_DEFAULTS > guardado manualmente
                peso_default_fob = FOB_DEFAULTS.get(prod, {}).get("peso_kg", 0.0)
                peso_final = float(peso_tn if peso_tn else (peso_default_fob if peso_default_fob else peso_saved))
                peso_input = cols[1].number_input(
                    "", value=peso_final,
                    min_value=0.0, step=0.01,
                    key=f"peso_{prod}", label_visibility="collapsed",
                    help="kg — se trae automáticamente de TN, o del histórico de compras"
                )
                fob_default = FOB_DEFAULTS.get(prod, {}).get("fob_usd", 0.0)
                fob_valor = float(fob_saved) if float(fob_saved) > 0 else float(fob_default)
                fob_input = cols[2].number_input(
                    "", value=fob_valor, min_value=0.0, step=0.5,
                    key=f"fob_{prod}", label_visibility="collapsed",
                    help="USD — precargado del promedio histórico de tus compras"
                )

                # Cálculo
                costo_import = round(peso_input * costo_kg_usd, 2)
                costo_total_usd = round(fob_input + costo_import, 2)
                costo_total_ars = round(costo_total_usd * tc_consolas)

                cols[3].markdown(f"**USD {costo_total_usd:,.2f}**")
                cols[4].markdown(f"**{fmt(costo_total_ars)}**")

                nuevos_costos[prod] = {
                    "fob_usd": fob_input,
                    "peso_kg": peso_input,
                    "costo_import_usd": costo_import,
                    "costo_total_usd": costo_total_usd,
                }

            st.divider()
            if st.button("💾 Guardar costos de consolas", use_container_width=True, type="primary"):
                st.session_state.costos_consolas = nuevos_costos
                ok = gs_write("CostosConsolas", nuevos_costos)
                if ok:
                    st.success("✅ Guardado en Google Sheets")
                else:
                    st.warning("⚠️ Guardado solo en sesión (Google Sheets no configurado)")

            # Tabla resumen
            st.divider()
            st.subheader("📊 Resumen de costos")
            resumen_rows = []
            for prod, data in nuevos_costos.items():
                if prod.startswith("_") or not isinstance(data, dict): continue
                resumen_rows.append({
                    "Producto": prod,
                    "Peso (kg)": data.get("peso_kg", 0),
                    "FOB (USD)": data.get("fob_usd", 0),
                    "Importación (USD)": data.get("costo_import_usd", 0),
                    "Costo total (USD)": data.get("costo_total_usd", 0),
                    "Costo total (ARS)": round(data.get("costo_total_usd", 0) * tc_consolas),
                })
            if resumen_rows:
                df_costos_res = pd.DataFrame(resumen_rows).sort_values("Costo total (USD)", ascending=False)
                st.dataframe(
                    df_costos_res.style.format({
                        "FOB (USD)": "${:,.2f}", "Importación (USD)": "${:,.2f}",
                        "Costo total (USD)": "${:,.2f}", "Costo total (ARS)": "${:,.0f}",
                        "Peso (kg)": "{:.3f}"
                    }),
                    use_container_width=True, hide_index=True
                )


else:
    st.info("👈 Seleccioná el período en el panel izquierdo y hacé clic en Buscar.")
