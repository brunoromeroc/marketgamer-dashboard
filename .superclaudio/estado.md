# Estado Market Gamer Dashboard

**Última sesión:** 2026-07-23 (/programar — margen verdadero USD + competencia)
**Modo activo:** /programar
**Versión actual:** v0.10.0 (margen USD histórico, KPI objetivo, piso+competencia)

---

## Sesión 2026-07-23 — Margen verdadero + posicionamiento competitivo

Contexto: Bruno quiere levantar el margen (25,3% pond. real). Se conectó el **MCP
oficial de Tienda Nube** (admin-mcp.tiendanube.com) a esta sesión — permite consultar
y editar catálogo/precios/stock en vivo. Se hizo relevamiento de competencia con 5
agentes → `docs/analisis-competencia-2026-07.md`.

### Implementado (todo en app.py, sintaxis OK + smoke tests pasan)
1. **Serie histórica del blue**: `get_blue_historico()` (Bluelytics evolution.json,
   4597 días, cache 24h) + `blue_en_fecha()` (busca hasta 7 días atrás en finde/feriado,
   fallback = dólar de hoy).
2. **Margen VERDADERO en USD** en 📈 Margen real: cada venta convertida al blue del
   día en que se vendió → neutro a la devaluación. KPIs (total/pond/unidad USD),
   brecha ARS-vs-USD explicada, evolución mensual USD/u, y columnas USD por producto
   en la tabla df_avg. Es el margen para curar precios.
3. **Margen objetivo** (slider en ⚙️ Config financiera, `cfg_margen_obj`, default 30% —
   elegido por Bruno). En Dashboard: card Margen bruto muestra "objetivo X% · ▲pp vs
   antes" + barra de progreso hacia la meta.
4. **Precio piso + semáforo competencia** en 💰 Precios: columnas Piso ($), Aire s/piso,
   Mercado med ($), Posición (🔴caro/🟢alineado/🔵barato/⭐solo). Datos en constante
   `COMPETENCIA` (snapshot 23/07/2026, regenerable). Resumen de oportunidades arriba
   de la tabla (subir/único/caro).

### Decisiones de Bruno (AskUserQuestion)
- Precios en TN: **no tocar todavía** — implementar dashboard primero, él ajusta luego.
- Margen objetivo: **30%**.
- RG 35XX y R36S (rojos estructurales): **dejar como están** por ahora (solo marcados
  en el semáforo). NO se liquidaron.

### Iteración (mismo día) — Rentabilidad reenfocada en 6 cuotas
- Bruno: ~50% de clientes paga en 6 cuotas y NUNCA ofrece 12. El margen a 6 cuotas
  es el piso real a proteger. Tabla "Rentabilidad por cuotas" → reenfocada:
  saca 12 cuotas, muestra solo margen 6c coloreado vs objetivo, ordenada peor-arriba,
  con columna **Acción** (a cuánto subir para asegurar el objetivo en 6c).
- Hallazgo clave: 30% a 6 cuotas es INALCANZABLE en productos competitivos (6c cuesta
  ~23,7% → IVA+tasa+objetivo = 64% del precio). Decisión de Bruno: cuando el precio
  p/objetivo supera el techo de mercado (COMPETENCIA.max × 1,05), marcar
  "⚠️ fuera de mercado → transferencia/débito" en vez de sugerir precio irreal.
  Productos "solo local" no tienen techo → sí sugiere subir.
- El gráfico de degradación por cuotas quedó dentro de un expander.

### Iteración (mismo día) — Limpieza tabla principal de Precios
Feedback de Bruno sobre la tabla de margen teórico (estaba recargada):
- Saca columnas: Marca, Piso, Aire, Costo full, Comisión, Envío, Uds vendidas.
  (El filtro de marca por pills SÍ queda; solo se sacó la columna.)
- Columnas finales: Producto · Precio · Mercado · Posición · Costo · Margen $ · Margen %.
- **Costo** ahora = total de Costos de consolas (FOB+import × dólar), no el "costo full".
- **Comisión del margen** = transferencia (~1,25%, PN real de Bruno), NO la vieja
  "tasa PN ponderada" (~14% que mezclaba transferencia+tarjeta — error conceptual).
  El peor caso (6c) ya vive en la tabla de abajo.
- **Mercado editable a mano**: expander con st.data_editor + botón guardar, persiste en
  sheet `PreciosCompetencia` (session key `precios_competencia`). El valor manual
  prevalece sobre el snapshot COMPETENCIA. Posición se recalcula del mercado efectivo.

### Pendiente inmediato
- Bruno revisa las 3 solapas con datos reales y valida.
- Cambios de precio en TN vía MCP: pendientes de que Bruno los apruebe uno por uno.
- Falta /smart-commit + push (no commiteado aún).

---

## Sesión 2026-07-06 — Rediseño solapa por solapa (decidido en conversación con Bruno)

Recorrimos el dashboard solapa por solapa discutiendo qué usa y qué no.
Todo lo decidido quedó implementado, commiteado y pusheado (7 commits, `1c9c834..99daf2c`).

### Decisión estructural: fuente única de verdad del P&L
- **`calcular_resultado_periodo()`** (app.py, junto a `costo_final_row`) es LA función
  del resultado financiero. La consumen: Salud Financiera, Dashboard y Analista IA.
- **NUNCA copiar la fórmula de margen inline en una solapa nueva** — antes había 4 copias
  con IVA 10.5% y packaging 2500 hardcodeados que podían divergir.
- Gastos fijos ahora se prorratean por los días reales del mes (antes /30 fijo).
- `kpi_card()` compartida reemplaza ~5 copias del mismo HTML de card.

### Config financiera global (sidebar, expander "⚙️ Config financiera")
- Dólar blue, IVA, pauta Meta y packaging son globales y **auto-aplicados sin botón**.
- La pauta se re-fetchea sola al cambiar el período (`_pauta_periodo` en session_state).
- Keys de session: `cfg_tc`, `cfg_iva`, `cfg_pauta`, `cfg_pkg` → espejados en
  `tipo_cambio_sf`, `pct_iva`, `pauta_manual`, `packaging_global`.
- `get_dolar_blue()` ahora cacheado 15 min (estaba sin cache, bug de decorador doble
  sobre `get_meta_spend` corregido).

### Menú: de 14 solapas a 12
- **📊 Dashboard** → resumen ejecutivo: card grande con resultado NETO del período
  (misma función que Salud) + delta vs período anterior equivalente (fetch liviano
  cacheado `_df_periodo_liviano`) + alertas accionables (productos sin costo,
  candidatas a efectivo, stock crítico). Top 10 facturación con prorrateo real.
  Se fueron: donuts de comisiones, toggle accesorios, cards por pasarela.
- **📦 Reposición** (fusión de Stock + Velocidad): stock se auto-carga al entrar
  (`_fetch_stock_tn()` con snapshot automático). Plan de compra: restock sugerido ×
  CostosConsolas → inversión USD/ARS, ganancia mensual estimada, repago, asignador
  por presupuesto (ganancia por dólar), pedido copiable. Inventario como expander.
- **💰 Precios** (ex Margen teórico): simulador inverso — FOB + margen objetivo →
  precio de lista sugerido **anclado a 6 cuotas** (regla real de Bruno: vende todo
  hasta 6 cuotas; el precio debe ser rentable en el peor caso). Redondeo a $5.000.
- **🏭 Proveedores: ELIMINADA** (~1050 líneas). Bruno ya no compara listas, pide
  directo. Parsers de catálogos/comparador/planificador viejos en git history.
  El contacto real del proveedor salió del código.
- **🔍 Detalle y ajustes**: detector de candidatas a efectivo (Convenir sin match MP)
  con marcado en 1 click. Se fueron los desgloses PN/MP, el resumen por medio de
  pago y la tabla de transacciones PN (duplicados de otras solapas).
- **💚 Salud Financiera**: consume la función única; sin doble fetch MP (reusa
  `st.session_state.mp_raw`); conciliación TN vs MP solo avisa si diff > 5%.
- **🤖 Analista IA**: contexto usa la función única (antes 4ta copia de la fórmula
  y omitía la pauta).

### Verificación
- Smoke test en bare mode forzando cada solapa (script en scratchpad, patcheando
  `st.radio`): **las 12 solapas pasan** con datos reales.
- Cazó y se arregló: `Restock sugerido` mezcla ints y "—" → coerción con
  `pd.to_numeric(errors="coerce")` antes de comparar.

## Decisiones de producto de Bruno (de la conversación)

1. Dashboard = resumen ejecutivo con neto real; iba directo a Salud Financiera.
2. Info repetida entre solapas → eliminarla sin miedo.
3. No usa: toggle accesorios, CSV de detalle (se dejó, es 1 botón), sliders de
   velocidad (rara vez), catálogos de proveedores, pedido WhatsApp viejo.
4. Compra reactivo hoy pero QUIERE reposición planificada con flujo → por eso el
   plan de compra con inversión/presupuesto en Reposición.
5. Vende todo en hasta 6 cuotas → pricing ancla en rentabilidad a 6 cuotas.
6. Gastos fijos los mantiene actualizados él.
7. Marca ventas en efectivo: importante pero no lo hacía → detector automático.

## Sesión 2026-07-06 (mañana) — Iteración post-revisión de Bruno

- Dashboard: evolución histórica mensual (fact/margen/órdenes/ticket con promedio),
  patrones por día de semana y momento del mes, tendencia por producto base
  (30d vs prom. 90d previos, flechas ±20%), alerta de sin-costo compactada.
- Salud Financiera: waterfall real (go.Waterfall) con % de cada costo sobre el
  total + caption "dónde atacar"; guardián de comisiones (avisa solo si el costo %
  de PN/MP se desvía >1pp del promedio histórico 12m); se retiró la tabla de
  detalle por orden (vive en Margen real).
- Bruno confirmó: usa muy poco "Detalle y ajustes" → candidata a achicarse o
  fusionarse (por ahora queda: tiene marcar-efectivo y debug de órdenes).
- Bruno tenía IVA en 0.00% en la config — avisado dos veces.

## Sesión 2026-07-06 (tarde) — Stock valuado + Audiencias

- Dashboard: sección "💼 Stock valuado" — snapshots de HistorialStock valuados a
  costo y precio de venta, KPIs de capital posicionado + curva de evolución.
  El Dashboard auto-carga stock y registra snapshot al abrirse.
- HistorialStock ya NO se borra: `compactar_historial()` en velocidad_restock
  (TDD, 5 tests nuevos, 25 total) — diario 180 días, semanal para atrás.
  La curva de capital crece de por vida. La historia arranca ~jun-2026 (TN no
  expone stock histórico; lo anterior no existe como dato).
- Nueva solapa "🎯 Audiencias" (para el equipo de paid media): geo de ventas
  reales por provincia/ciudad (procesar_orders ahora captura Ciudad),
  concentración 80/20, demografía edad×género de Meta Ads con CPA/ROAS por
  segmento (`get_meta_demograficos`), y resumen copiable para el media buyer.
- Menú quedó en 13 solapas.

## Pendiente para próximas sesiones

1. **Bruno debe revisar** las solapas nuevas al despertar (Dashboard, Reposición,
   Precios) y validar números contra Salud Financiera.
2. Pregunta abierta que quedó sin responder: ¿usa 💳 Estadísticas de pago? Si no,
   candidata a reducirse a un bloque dentro de Salud Financiera.
3. Pendiente de Bruno: decir qué bloques de Salud Financiera scrollea sin mirar
   (waterfall, detalle por orden, tendencia) para podar.
4. Web/Analytics: dos funciones de matching casi idénticas (`_match`/`_mt`) y
   expanders de debug en producción — candidata a limpieza futura.
5. Ideas que quedaron: webhook de PN para liquidaciones reales; override IIBB.

## Contexto importante (invariantes)

- Exchange rate: SIEMPRE dólar blue (nunca oficial)
- Precios: SIEMPRE precio unitario de TN API, NUNCA dividir total por cantidad
- El margen confiable ahora es el mismo en Dashboard, Salud Financiera y Analista IA
  (función única) — la vieja regla "solo confiar en Tab 3" quedó obsoleta
- UI: español argentino con voseo
- Pasarelas: PN (transferencias) + MP (resto, incluye links manuales "a convenir")
- NUNCA inventar números sin data real; tasas oficiales públicas OK como fallback
- Persistencia de lo manual (efectivo, costos, gastos) en Google Sheets

## Último commit

`99daf2c fix(reposicion): coercionar 'Restock sugerido' que mezcla ints y '—'`
