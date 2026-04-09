# Proveedores Tab — Rediseño completo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rediseñar la solapa Proveedores (tab10) de `app.py` con 3 secciones: reemplazo de catálogo con diff de precios, comparador cross-proveedor con fuzzy matching, y planificador de compra integrado con stock de TN.

**Architecture:** Todo el cambio ocurre en `app.py`. Se agregan 4 funciones helper antes del bloque de tabs, y se reescribe completamente el bloque `with tab10:` (actualmente líneas 2118–2698). Sin archivos nuevos.

**Tech Stack:** Python 3.14, Streamlit 1.54, pandas, python-pptx (nuevo), difflib (stdlib), gspread.

---

## File Map

| Archivo | Acción | Qué cambia |
|---|---|---|
| `requirements.txt` | Modificar | Agregar `python-pptx` |
| `app.py` | Modificar — antes de línea ~540 (bloque de tabs) | Agregar 4 funciones helper: `compute_catalog_diff`, `parse_pptx_catalog`, `fuzzy_group_products`, `get_stock_for_planner` |
| `app.py` | Modificar — líneas 2118–2698 | Reescribir `with tab10:` completo con 3 secciones |

---

## Task 1: Agregar dependencia python-pptx

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Agregar python-pptx a requirements.txt**

El archivo actual tiene 6 líneas. Agregar `python-pptx` al final:

```
streamlit
requests
pandas
plotly
gspread
google-auth
python-pptx
```

- [ ] **Step 2: Instalar la dependencia**

```bash
python3 -m pip install python-pptx
```

Salida esperada: `Successfully installed python-pptx-X.X.X` (o `already satisfied` si ya estaba).

- [ ] **Step 3: Verificar import**

```bash
python3 -c "from pptx import Presentation; print('OK')"
```

Salida esperada: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add python-pptx for PowerPoint catalog parsing"
```

---

## Task 2: Funciones helper de proveedores

**Files:**
- Modify: `app.py` — insertar antes de la línea que tiene `# ── Config ─` (línea ~12) o inmediatamente después de la función `_normalizar` (línea ~32)

Buscar en `app.py` el bloque:
```python
def _normalizar(s):
    return re.sub(r'\s+', ' ', str(s).strip().lower())
```

Insertar el siguiente bloque **inmediatamente después** de esa función:

- [ ] **Step 1: Insertar las 4 funciones helper después de `_normalizar`**

```python
# ── Proveedores helpers ────────────────────────────────────────────────────────
from datetime import date as _date

def compute_catalog_diff(old_products: dict, new_products: dict) -> list:
    """Compara dos catálogos y devuelve lista de cambios (cambiado/nuevo/eliminado)."""
    diff = []
    old_keys = set(old_products.keys())
    new_keys = set(new_products.keys())
    for name in old_keys & new_keys:
        old_price = float(old_products[name].get("precio_usd", 0))
        new_price = float(new_products[name].get("precio_usd", 0))
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
    """Extrae filas (Producto, FOB USD, Storage) de un PowerPoint de lista de precios."""
    from pptx import Presentation
    import io
    rows = []
    seen = set()
    try:
        prs = Presentation(io.BytesIO(file_bytes))
    except Exception:
        return []
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_table:
                continue
            table = shape.table
            for row_idx in range(len(table.rows)):
                cells = [cell.text.strip() for cell in table.rows[row_idx].cells]
                for i, cell in enumerate(cells):
                    try:
                        val = float(
                            cell.replace("$", "").replace(",", "").replace("USD", "").strip()
                        )
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
                        rows.append({
                            "Producto": nombre,
                            "FOB (USD)": val,
                            "Marca": "—",
                            "Pantalla": "—",
                            "CPU": "—",
                            "Storage": storage,
                        })
                        break
                    except ValueError:
                        continue
    return rows


def fuzzy_group_products(suppliers: dict, threshold: float = 0.80) -> pd.DataFrame:
    """
    Agrupa productos similares de distintos proveedores usando difflib.
    Devuelve DataFrame con Producto | Proveedor1 | Proveedor2 | ...
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
        total = 0
        unlimited = False
        for v in p.get("variants", []):
            s = v.get("stock", None)
            if s is None:
                unlimited = True
                break
            total += int(s)
        stock_dict[nombre] = None if unlimited else total
    return stock_dict
```

- [ ] **Step 2: Verificar que app.py parsea sin errores**

```bash
python3 -c "
import ast
with open('app.py', encoding='utf-8') as f:
    ast.parse(f.read())
print('Syntax OK')
"
```

Salida esperada: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add proveedores helper functions (diff, pptx parser, fuzzy group, stock)"
```

---

## Task 3: Tab10 — Sección 1: Catálogos con replace flow

**Files:**
- Modify: `app.py` — reemplazar el bloque `with tab10:` (líneas ~2118–2698)

El bloque comienza con:
```python
    with tab10:
        st.subheader("🏭 Proveedores — Catálogos y comparación")
```

Y termina justo antes de:
```python
else:
```
(la última línea del archivo, ~línea 2699).

- [ ] **Step 1: Reemplazar el bloque `with tab10:` con la Sección 1 completa + stubs para Secciones 2 y 3**

Reemplazar todo el bloque `with tab10:` (desde `    with tab10:` hasta el `st.divider()` + botón global de guardado inclusive) con:

```python
    with tab10:
        st.subheader("🏭 Proveedores — Catálogos, Comparación y Compras")

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

        # ════════════════════════════════════════════════════════════════════
        # SECCIÓN 1: CATÁLOGOS
        # ════════════════════════════════════════════════════════════════════
        st.subheader("📁 Catálogos")
        st.caption("Cada proveedor muestra sus productos y la fecha de la última lista. Subí una nueva lista para reemplazar el catálogo y ver qué cambió.")

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
                        for page in pdf.pages:
                            tables = page.extract_tables()
                            for table in tables:
                                for row in table:
                                    if not row:
                                        continue
                                    cells = [str(c).strip() if c else "" for c in row]
                                    for i, cell in enumerate(cells):
                                        try:
                                            val = float(cell.replace("$", "").replace(",", ""))
                                            if not (1 < val < 5000):
                                                continue
                                            nombre_parts = [c for c in cells[:i] if c and len(c) > 2 and not c.replace(".", "").isdigit()]
                                            if nombre_parts:
                                                storage = "—"
                                                for c in cells:
                                                    if any(s in c.upper() for s in ["64G", "128G", "256G", "32G", "16G", "512G"]):
                                                        storage = c.strip()
                                                        break
                                                raw_rows.append({
                                                    "Producto": nombre_parts[0],
                                                    "FOB (USD)": val,
                                                    "Marca": "—", "Pantalla": "—", "CPU": "—", "Storage": storage,
                                                })
                                                break
                                        except ValueError:
                                            continue
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

            with st.expander(f"**{sup_name}** — {prod_count} productos · Última lista: {updated}"):
                st.caption(f"📞 {sup_data.get('contacto', '—')} | 🌐 {sup_data.get('web', '—')}")

                if sup_data.get("productos"):
                    df_cat = pd.DataFrame([
                        {"Producto": n, "FOB (USD)": float(info.get("precio_usd", 0)),
                         "Marca": info.get("marca", "—"), "Storage": info.get("storage", "—")}
                        for n, info in sup_data["productos"].items()
                    ]).sort_values("FOB (USD)")
                    st.dataframe(
                        df_cat.style.format({"FOB (USD)": "${:.1f}"}),
                        use_container_width=True, hide_index=True,
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
        # SECCIÓN 2: COMPARADOR  [STUB — Task 4]
        # ════════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("⚖️ Comparador de precios")
        st.info("Comparador en construcción — próxima tarea.")

        # ════════════════════════════════════════════════════════════════════
        # SECCIÓN 3: PLANIFICADOR  [STUB — Task 5]
        # ════════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("🛒 Planificador de compra")
        st.info("Planificador en construcción — próxima tarea.")

        # ── Guardado global ──
        st.divider()
        if st.button("💾 Guardar todos los datos de proveedores", use_container_width=True):
            ok = gs_write("Proveedores", st.session_state.proveedores_data)
            st.success("✅ Guardado en Google Sheets" if ok else "⚠️ Solo en sesión")
```

- [ ] **Step 2: Verificar sintaxis**

```bash
python3 -c "
import ast
with open('app.py', encoding='utf-8') as f:
    ast.parse(f.read())
print('Syntax OK')
"
```

- [ ] **Step 3: Arrancar el dashboard y verificar Sección 1**

```bash
python3 -m streamlit run app.py
```

Verificar en `http://localhost:8501` → tab Proveedores:
- ✅ Se ven los proveedores con fecha de última lista
- ✅ Cada proveedor tiene su tabla de productos expandible
- ✅ File uploader acepta CSV, Excel, PDF, PPTX
- ✅ Al subir un archivo CSV simple, se muestra la tabla de diff y el botón de confirmar
- ✅ Las secciones 2 y 3 muestran el mensaje "en construcción"

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: proveedores tab - seccion 1 catalogo con replace flow y diff de precios"
```

---

## Task 4: Tab10 — Sección 2: Comparador con fuzzy matching

**Files:**
- Modify: `app.py` — reemplazar el stub de Sección 2

Buscar este bloque exacto en `app.py`:
```python
        # ════════════════════════════════════════════════════════════════════
        # SECCIÓN 2: COMPARADOR  [STUB — Task 4]
        # ════════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("⚖️ Comparador de precios")
        st.info("Comparador en construcción — próxima tarea.")
```

Reemplazarlo con:

- [ ] **Step 1: Reemplazar stub de Sección 2 con el comparador completo**

```python
        # ════════════════════════════════════════════════════════════════════
        # SECCIÓN 2: COMPARADOR
        # ════════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("⚖️ Comparador de precios")
        st.caption("Todos los productos de todos los proveedores en una tabla. ✅ = precio más barato para ese producto.")

        if len(suppliers) < 1:
            st.info("Cargá al menos un proveedor para ver la comparación.")
        else:
            buscar_comp = st.text_input("🔍 Buscar producto", key="search_comparador")
            df_fuzzy = fuzzy_group_products(suppliers)

            if df_fuzzy.empty:
                st.info("No hay productos cargados en los catálogos.")
            else:
                if buscar_comp:
                    df_fuzzy = df_fuzzy[
                        df_fuzzy["Producto"].str.contains(buscar_comp, case=False, na=False)
                    ]

                sup_cols = [c for c in df_fuzzy.columns if c != "Producto"]

                def _highlight_cheapest(row):
                    styles = [""] * len(row)
                    prices = [
                        (i + 1, row[c])
                        for i, c in enumerate(sup_cols)
                        if pd.notna(row[c]) and row[c] > 0
                    ]
                    if prices:
                        min_i = min(prices, key=lambda x: x[1])[0]
                        styles[min_i] = "background-color: #1a3a1a; color: #4caf50; font-weight: bold"
                    return styles

                fmt = {col: "${:.1f}" for col in sup_cols}
                st.dataframe(
                    df_fuzzy.style
                        .apply(_highlight_cheapest, axis=1)
                        .format(fmt, na_rep="—"),
                    use_container_width=True,
                    hide_index=True,
                )

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
                            f"Mejor proveedor": f"{best_sup} ${fob_prov:.1f}",
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
```

- [ ] **Step 2: Verificar sintaxis**

```bash
python3 -c "
import ast
with open('app.py', encoding='utf-8') as f:
    ast.parse(f.read())
print('Syntax OK')
"
```

- [ ] **Step 3: Verificar en el dashboard**

```bash
python3 -m streamlit run app.py
```

Verificar en tab Proveedores → Sección 2:
- ✅ Aparece tabla con todos los productos de todos los proveedores
- ✅ La celda más barata de cada fila tiene fondo verde
- ✅ El buscador filtra la tabla en tiempo real
- ✅ Si hay datos en CostosConsolas, se muestra la comparación con el dashboard

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: proveedores tab - seccion 2 comparador con fuzzy matching y highlight"
```

---

## Task 5: Tab10 — Sección 3: Planificador de compra

**Files:**
- Modify: `app.py` — reemplazar el stub de Sección 3

Buscar este bloque exacto en `app.py`:
```python
        # ════════════════════════════════════════════════════════════════════
        # SECCIÓN 3: PLANIFICADOR  [STUB — Task 5]
        # ════════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("🛒 Planificador de compra")
        st.info("Planificador en construcción — próxima tarea.")
```

Reemplazarlo con:

- [ ] **Step 1: Reemplazar stub de Sección 3 con el planificador completo**

```python
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
                        for p_name, p_info in sup_data.get("productos", {}).items():
                            ratio = _SM(None, _normalizar(prod_name), _normalizar(p_name)).ratio()
                            if ratio >= 0.80:
                                candidates.append((sup_name, float(p_info.get("precio_usd", 0))))
                                break
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
```

- [ ] **Step 2: Verificar sintaxis**

```bash
python3 -c "
import ast
with open('app.py', encoding='utf-8') as f:
    ast.parse(f.read())
print('Syntax OK')
"
```

- [ ] **Step 3: Verificar en el dashboard**

```bash
python3 -m streamlit run app.py
```

Verificar en tab Proveedores → Sección 3:
- ✅ Botón "Cargar stock" aparece y al hacer clic consulta TN sin errores
- ✅ Después de cargar, aparece la tabla con columnas: Producto, Stock, Urgencia, Precio, Proveedor, checkbox Comprar, input Cantidad
- ✅ Los productos con stock bajo aparecen primero (🔴 Crítico arriba)
- ✅ Al tildar productos y poner cantidades, aparece el resumen debajo
- ✅ El resumen muestra totales por proveedor y total general
- ✅ El bloque de código al final es copiable

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: proveedores tab - seccion 3 planificador de compra con resumen por proveedor"
```

---

## Checklist final

Antes de cerrar, verificar en el dashboard que las 3 secciones conviven:

- [ ] Sección 1: Subir un archivo PPTX → se muestra tabla de diff → confirmar → catálogo reemplazado con fecha de hoy
- [ ] Sección 1: Subir un archivo CSV → misma experiencia
- [ ] Sección 2: Tabla comparadora muestra todos los proveedores con celdas verdes en el más barato
- [ ] Sección 2: Buscador filtra la tabla
- [ ] Sección 3: Cargar stock → tabla de planificación → seleccionar productos → resumen generado → texto copiable
- [ ] Botón "Guardar todos los datos" al final del tab sigue funcionando
