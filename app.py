import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
import time

TN_TOKEN = st.secrets["TN_TOKEN"]
TN_STORE_ID = st.secrets["TN_STORE_ID"]

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
for key in ["df_tn", "df_pagos", "costos_productos", "ordenes_efectivo", "ids_venta_local"]:
    if key not in st.session_state:
        if key == "costos_productos":
            st.session_state[key] = {}
        elif key in ["ordenes_efectivo", "ids_venta_local"]:
            st.session_state[key] = set()
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

def procesar_orders(orders):
    filas = []
    for o in orders:
        prods = []
        for p in o.get("products", []):
            n = p.get("name", "")
            nombre = n if isinstance(n, str) else (n.get("es", "") or next(iter(n.values()), "")) if isinstance(n, dict) else ""
            prods.append(nombre)
        productos = " / ".join(prods)
        cantidad = sum(p.get("quantity", 1) for p in o.get("products", []))

        # Medio de pago y cuotas
        pd_raw = o.get("payment_details", {})
        medio = o.get("payment_provider_id") or o.get("gateway") or ""
        cuotas = 1
        if isinstance(pd_raw, list) and pd_raw:
            medio = pd_raw[0].get("payment_method", medio)
            cuotas = int(pd_raw[0].get("installments", 1) or 1)
        elif isinstance(pd_raw, dict):
            medio = pd_raw.get("payment_method", medio)
            cuotas = int(pd_raw.get("installments", 1) or 1)

        try: fecha = pd.to_datetime(o.get("created_at", "")).strftime("%Y-%m-%d")
        except: fecha = ""

        total       = float(o.get("total", 0))
        descuento   = float(o.get("discount", 0) or 0)
        costo_envio = float(o.get("shipping_cost_customer", 0) or 0)

        # Costos de Pago Nube
        gateway_cost = float(o.get("gateway_cost", 0) or 0)
        comision_pn  = 0.0
        costo_fin_pn = 0.0
        otros_costos = 0.0
        if isinstance(pd_raw, list):
            for gw in pd_raw:
                if isinstance(gw, dict):
                    comision_pn  += float(gw.get("commission", 0) or 0)
                    costo_fin_pn += float(gw.get("financing_cost", 0) or 0)
                    otros_costos += float(gw.get("other_costs", 0) or 0)
        elif isinstance(pd_raw, dict):
            comision_pn  = float(pd_raw.get("commission", 0) or 0)
            costo_fin_pn = float(pd_raw.get("financing_cost", 0) or 0)
            otros_costos = float(pd_raw.get("other_costs", 0) or 0)

        # Si no hay desglose usar gateway_cost
        if comision_pn == 0 and costo_fin_pn == 0:
            comision_pn = gateway_cost

        total_costos_pn = comision_pn + costo_fin_pn + otros_costos
        neto = round(total - total_costos_pn, 2)
        pct_costo = round((total_costos_pn / total * 100) if total > 0 else 0, 2)

        filas.append({
            "Orden": o.get("number"),
            "Fecha": fecha,
            "Cliente": str(o.get("contact_name", "")),
            "Medio de Pago": str(medio).strip(),
            "Cuotas": cuotas,
            "Total ($)": total,
            "Descuento ($)": descuento,
            "Costo Envio ($)": costo_envio,
            "Comision PN ($)": round(comision_pn, 2),
            "Costo Financiero ($)": round(costo_fin_pn, 2),
            "Otros Costos ($)": round(otros_costos, 2),
            "Total Costos PN ($)": round(total_costos_pn, 2),
            "Costo PN (%)": pct_costo,
            "Neto ($)": neto,
            "Estado Envio": o.get("shipping_status", ""),
            "Productos": productos,
            "Cantidad": cantidad,
            "Canal": str(o.get("app_id", "tiendanube")),
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
        st.session_state.df_tn = procesar_orders(orders)
        st.success(f"✅ {len(orders)} órdenes cargadas desde Tienda Nube")
    else:
        st.session_state.df_tn = pd.DataFrame()
        st.info("No se encontraron órdenes en el período.")

    pagos = get_tn_pagos(fecha_desde, fecha_hasta)
    if pagos:
        st.session_state.df_pagos = procesar_pagos_pn(pagos)
    else:
        st.session_state.df_pagos = pd.DataFrame()

    st.session_state.ordenes_efectivo = set()
    st.session_state.ids_venta_local = set()

# ── Tabs ───────────────────────────────────────────────────────────────────────
if st.session_state.df_tn is not None:
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dashboard",
        "🔍 Detalle y ajustes",
        "🔗 Conciliación TN vs Pago Nube",
        "💚 Salud Financiera",
        "📦 Stock"
    ])
    df_tn = st.session_state.df_tn.copy()
    df_pagos = st.session_state.df_pagos.copy() if st.session_state.df_pagos is not None else pd.DataFrame()

    # ── TAB 1: DASHBOARD ──────────────────────────────────────────────────────
    with tab1:
        st.subheader("🛍️ Tienda Nube")
        if df_tn.empty:
            st.info("No hay órdenes en este período.")
        else:
            k1, k2, k3, k4, k5, k6 = st.columns(6)
            k1.metric("Órdenes", len(df_tn))
            k2.metric("Facturación bruta", fmt(df_tn["Total ($)"].sum()))
            k3.metric("Descuentos", fmt(df_tn["Descuento ($)"].sum()))
            k4.metric("Comision PN", fmt(df_tn["Comision PN ($)"].sum()))
            k5.metric("Costo Financiero", fmt(df_tn["Costo Financiero ($)"].sum()))
            k6.metric("💰 Neto real", fmt(df_tn["Neto ($)"].sum()))

            col_a, col_b = st.columns(2)
            with col_a:
                pie_medio = df_tn.groupby("Medio de Pago")["Total ($)"].sum().reset_index()
                st.plotly_chart(px.pie(
                    pie_medio, names="Medio de Pago", values="Total ($)", hole=0.4,
                    title="Distribución por medio de pago", color_discrete_sequence=COLORES
                ), use_container_width=True)
            with col_b:
                fig_dia = px.bar(
                    df_tn.groupby("Fecha")["Total ($)"].sum().reset_index(),
                    x="Fecha", y="Total ($)", title="Ventas por día",
                    color_discrete_sequence=["#009EE3"]
                )
                fig_dia.update_layout(yaxis_tickformat="$,.0f")
                st.plotly_chart(fig_dia, use_container_width=True)

            col_c, col_d = st.columns(2)
            with col_c:
                canal_data = df_tn.groupby("Canal")["Total ($)"].sum().reset_index()
                st.plotly_chart(px.pie(
                    canal_data, names="Canal", values="Total ($)", hole=0.4,
                    title="Por canal de venta", color_discrete_sequence=COLORES
                ), use_container_width=True)
            with col_d:
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

        if not df_pagos.empty:
            st.divider()
            st.subheader("💳 Pago Nube")
            p1, p2, p3 = st.columns(3)
            pagos_ok = df_pagos[df_pagos["Estado"] == "paid"] if not df_pagos.empty else pd.DataFrame()
            p1.metric("Transacciones aprobadas", len(pagos_ok))
            p2.metric("Total cobrado", fmt(pagos_ok["Monto ($)"].sum()) if not pagos_ok.empty else "$0")
            p3.metric("Total transacciones", len(df_pagos))

    # ── TAB 2: DETALLE ────────────────────────────────────────────────────────
    with tab2:
        st.subheader("🛍️ Detalle de órdenes — Tienda Nube")
        if df_tn.empty:
            st.info("No hay órdenes en este período.")
        else:
            cols_tn = ["Orden", "Fecha", "Cliente", "Medio de Pago", "Cuotas", "Total ($)",
                       "Descuento ($)", "Costo Envio ($)", "Comision PN ($)", "Costo Financiero ($)",
                       "Otros Costos ($)", "Total Costos PN ($)", "Costo PN (%)", "Neto ($)",
                       "Estado Envio", "Productos", "Cantidad", "Canal"]
            cols_tn = [c for c in cols_tn if c in df_tn.columns]
            st.dataframe(
                df_tn[cols_tn].style.format({
                    "Total ($)": "${:,.0f}", "Descuento ($)": "${:,.0f}",
                    "Costo Envio ($)": "${:,.0f}", "Comision PN ($)": "${:,.0f}",
                    "Costo Financiero ($)": "${:,.0f}", "Otros Costos ($)": "${:,.0f}",
                    "Total Costos PN ($)": "${:,.0f}", "Costo PN (%)": "{:.2f}%", "Neto ($)": "${:,.0f}",
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
                CostoFin=("Costo Financiero ($)", "sum"),
                TotalCostos=("Total Costos PN ($)", "sum"),
                Neto=("Neto ($)", "sum"),
            ).reset_index()
            res["Costo %"] = (res["TotalCostos"] / res["Bruto"] * 100).round(2).apply(fmt_pct)
            for col in ["Bruto", "Comision", "CostoFin", "TotalCostos", "Neto"]:
                res[col] = res[col].apply(fmt)
            res.columns = ["Medio de Pago", "Cantidad", "Bruto ($)", "Comision PN ($)", "Costo Fin. ($)", "Total Costos ($)", "Neto ($)", "Costo %"]
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

    # ── TAB 3: CONCILIACIÓN ───────────────────────────────────────────────────
    with tab3:
        st.subheader("🔗 Conciliación Tienda Nube vs Pago Nube")
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

        with st.expander("⚙️ Configuración", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                tipo_cambio = st.number_input("💵 Tipo de cambio (ARS/USD)", value=1200, step=10)
            with col2:
                pct_iva = st.slider("🧾 IVA efectivo (%)", min_value=0.0, max_value=21.0, value=10.5, step=0.5,
                    help="Configurá el IVA según tu régimen fiscal")
            with col3:
                pauta_manual = st.number_input("📣 Pauta publicitaria del período (ARS)", value=0, step=50_000)

        st.divider()
        st.subheader("💰 Costos por producto")
        st.caption("Cargá el costo en USD de cada producto para calcular márgenes.")

        if df_tn.empty:
            st.info("Buscá primero para ver los productos.")
        else:
            # Obtener lista de productos únicos vendidos
            productos_vendidos = {}
            for _, row in df_tn.iterrows():
                for p in str(row.get("Productos", "")).split(" / "):
                    p = p.strip()
                    if p:
                        productos_vendidos[p] = productos_vendidos.get(p, 0) + row.get("Cantidad", 1)

            costos = st.session_state.costos_productos.copy()

            with st.form("form_costos"):
                st.markdown("**Cargá el costo en USD de cada producto:**")
                cols_h = st.columns([3, 1, 1])
                cols_h[0].markdown("**Producto**")
                cols_h[1].markdown("**Unidades vendidas**")
                cols_h[2].markdown("**Costo (USD)**")

                nuevos_costos = {}
                for prod, qty in sorted(productos_vendidos.items(), key=lambda x: -x[1]):
                    cols = st.columns([3, 1, 1])
                    cols[0].write(prod)
                    cols[1].write(str(qty))
                    costo_actual = costos.get(prod, 0.0)
                    nuevo_costo = cols[2].number_input("", value=float(costo_actual), min_value=0.0,
                        step=0.01, key=f"costo_{prod}", label_visibility="collapsed")
                    nuevos_costos[prod] = nuevo_costo

                if st.form_submit_button("💾 Guardar costos", use_container_width=True):
                    st.session_state.costos_productos = nuevos_costos
                    costos = nuevos_costos
                    st.success("✅ Costos guardados.")

            # Calcular resultados
            facturacion_bruta = df_tn["Total ($)"].sum()
            facturacion_neta = df_tn["Neto ($)"].sum()
            costo_iva = facturacion_bruta * (pct_iva / 100)
            comisiones_pn = df_tn["Comision PN ($)"].sum()

            # Costo de productos
            costo_productos_total = 0
            detalle_prods = []
            for prod, qty in productos_vendidos.items():
                costo_usd = costos.get(prod, 0)
                costo_ars = costo_usd * tipo_cambio * qty
                costo_productos_total += costo_ars
                detalle_prods.append({
                    "Producto": prod,
                    "Unidades": qty,
                    "Costo Unit. USD": costo_usd,
                    "Costo Unit. ARS": round(costo_usd * tipo_cambio),
                    "Costo Total ARS": round(costo_ars),
                    "Margen por unidad": round(
                        (df_tn[df_tn["Productos"].str.contains(prod, na=False)]["Total ($)"].sum() / qty
                        - costo_usd * tipo_cambio), 2
                    ) if qty > 0 else 0,
                })

            dias = (fecha_hasta - fecha_desde).days + 1
            ganancia_bruta = facturacion_neta - costo_iva - costo_productos_total
            resultado_final = ganancia_bruta - pauta_manual

            st.divider()
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("💰 Facturación bruta", fmt(facturacion_bruta))
            k2.metric("💳 Comisiones PN", fmt(comisiones_pn), delta=f"-{fmt(comisiones_pn)}", delta_color="inverse")
            k3.metric(f"🧾 IVA ({pct_iva:.1f}%)", fmt(costo_iva), delta=f"-{fmt(costo_iva)}", delta_color="inverse")
            k4.metric("📦 Costo productos", fmt(costo_productos_total), delta=f"-{fmt(costo_productos_total)}", delta_color="inverse")

            st.divider()
            g1, g2 = st.columns(2)
            g1.metric("📊 Ganancia antes de pauta", fmt(ganancia_bruta))
            g2.metric("📣 Pauta publicitaria", fmt(pauta_manual), delta=f"-{fmt(pauta_manual)}", delta_color="inverse")
            st.divider()
            st.metric(f"{'🟢' if resultado_final >= 0 else '🔴'} RESULTADO FINAL DEL PERÍODO", fmt(resultado_final))
            if resultado_final >= 0:
                st.success(f"✅ Resultado positivo: {fmt(resultado_final)}")
            else:
                st.error(f"⚠️ Resultado negativo: -{fmt(abs(resultado_final))}")

            # Tabla de detalle
            if detalle_prods:
                st.divider()
                st.subheader("📋 Detalle por producto")
                df_det = pd.DataFrame(detalle_prods)
                st.dataframe(df_det.style.format({
                    "Costo Unit. ARS": "${:,.0f}",
                    "Costo Total ARS": "${:,.0f}",
                    "Margen por unidad": "${:,.0f}",
                }), use_container_width=True, hide_index=True)

            # Cascada
            st.divider()
            st.subheader("📊 Cascada de resultados")
            wf = pd.DataFrame({
                "Concepto": ["Facturación bruta", "Comisiones PN", f"IVA ({pct_iva:.1f}%)", "Costo productos", "Pauta", "Resultado final"],
                "Monto": [facturacion_bruta, -comisiones_pn, -costo_iva, -costo_productos_total, -pauta_manual, resultado_final],
                "Color": ["#00C49F", "#FF9900", "#FF5733", "#FF5733", "#FF9900", "#009EE3" if resultado_final >= 0 else "#FF0000"],
            })
            fig_wf = px.bar(wf, x="Concepto", y="Monto", color="Concepto",
                color_discrete_sequence=wf["Color"].tolist(), title="Cascada financiera del período")
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

else:
    st.info("👈 Seleccioná el período en el panel izquierdo y hacé clic en Buscar.")
