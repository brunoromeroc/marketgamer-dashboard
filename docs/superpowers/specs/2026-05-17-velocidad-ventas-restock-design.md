# Diseño — Rediseño solapa "Velocidad de ventas y planificación de restock"

Fecha: 2026-05-17
Estado: aprobado, pendiente de plan de implementación

## Problema

La solapa "🔥 Velocidad de ventas" ([app.py:3800-3946](../../../app.py)) tiene tres
fallas que llevan a decisiones de compra equivocadas:

1. **Velocidad diluida por días sin stock.** `vel_dia = unidades / dias_periodo`
   ([app.py:3837](../../../app.py)) divide por los días de calendario del período
   elegido. Un producto que estuvo sin stock 200 de 229 días igual se divide por
   229, subestimando la demanda justo de los productos que se quiebran (los que
   más importa reponer).
2. **Acoplada al selector de período lateral.** `df_tn` viene filtrado por la
   fecha del sidebar, así que la velocidad cambia según el período elegido —
   inútil para planificar compras, que necesitan un dato estable.
3. **Restock y alertas a ojo y ruidosas.** `restock = vel*30 - stock + vel*lead`
   con el 30 hardcodeado ([app.py:3848](../../../app.py)); urgencia con fórmula
   inventada ([app.py:3854](../../../app.py)); alertas que gritan "crítico" aun
   cuando el propio motor sugiere pedir 0 unidades.

Bug de base detectado: en `procesar_orders` ([app.py:2033](../../../app.py)) la
cantidad por línea se aplana a `Cantidad` total de la orden. La solapa, al no
tener cantidad por producto, asigna la cantidad total a **cada** producto de una
orden multi-producto, inflando las unidades.

## Restricción de datos (investigada)

- La integración TN (`get_tn_products`, [app.py:3732](../../../app.py)) trae
  **solo el stock actual** de cada variante. No hay log de movimientos ni
  historial: la API como está integrada no expone "cuándo tocó 0".
- `gs_write` ([app.py:730](../../../app.py)) **pisa** el dato (`ws.clear()`): es
  un único JSON, no una serie temporal. Para historial hace falta un patrón que
  agregue, no que sobrescriba.

Decisión: **proxy retroactivo (A) + snapshot diario desde ahora (B) combinados.**
A arregla el número hoy; B construye la verdad exacta hacia adelante.

## Decisiones de diseño (Q&A con el usuario)

| # | Decisión |
|---|----------|
| 1 | Estrategia de datos: proxy A + snapshot diario B combinados |
| 2 | Mostrar velocidad histórica **y** reciente lado a lado; restock usa la reciente |
| 3 | Denominador proxy: primera venta → hoy (si hay stock) / → última venta (si está en 0); híbrido con snapshot real donde exista |
| 4 | Modelo de restock estándar: ROP = vel·lead + stock_seguridad; 3 perillas globales |
| 5 | Alertas: (a) no alertar sin acción + (b) flag baja confianza + (c) ranking por facturación en riesgo |
| 6 | Snapshot al cargar stock / "Actualizar datos", idempotente por fecha, retención 180 días |
| 7 | Fix de conteo de raíz: columna estructurada por línea en `df_tn` |

## Arquitectura

Tres piezas nuevas, todas en `app.py` (se respeta el patrón del proyecto):

### 3.1 Captura de stock por línea (fix H)

En `procesar_orders` ([app.py:2021](../../../app.py)) agregar al dict de fila una
columna nueva `Items`: lista de `{"producto": nombre, "cantidad": qty, "costo": cost}`
por cada producto de la orden. Las solapas existentes siguen usando
`Productos`/`Cantidad` sin modificarse (cambio aditivo, bajo riesgo).

### 3.2 Historial de stock (parte B)

- Clave nueva en Sheets: `HistorialStock`, formato `{fecha_iso: {producto: stock}}`.
- Helper nuevo `gs_append_snapshot(stock_map)`:
  1. Lee el dict actual con `gs_read("HistorialStock")`.
  2. Agrega/pisa la entrada de la fecha de hoy (idempotente por día).
  3. Recorta a las últimas 180 fechas.
  4. Reescribe con `gs_write("HistorialStock", ...)`.
- Se invoca al cargar stock desde TN ([app.py:3730](../../../app.py)) y al tocar
  "Actualizar datos".
- Stock agregado por **nombre de producto** (suma de variantes), consistente con
  [app.py:3828](../../../app.py).

### 3.3 Motor de velocidad/restock

Función nueva aislada `calcular_velocidad_restock(df_tn, stock_map, historial_stock, params)`
que reemplaza el bloque [app.py:3835-3873](../../../app.py). Testeable sola.

Por producto calcula:

**Unidades reales** desde `Items` (no desde `Cantidad` de la orden).

**Dos velocidades:**
- `vel_historica` = unidades / días con stock, sobre toda la historia disponible.
- `vel_reciente` = ídem, ventana últimos N días (slider, default 90).

**Días con stock (denominador), por tramo:**
- Tramo con snapshot en `HistorialStock` → días reales donde `stock > 0`.
- Tramo sin snapshot (pasado) → proxy: desde la primera venta del producto en la
  ventana hasta:
  - **hoy**, si el producto tiene stock ahora (> 0);
  - **la última venta**, si está en 0 ahora.
- Denominador mínimo 1 día (evita división por cero).

**Modelo de restock** (usa `vel_reciente`), 3 perillas globales en el expander
"⚙️ Configuración de alertas":
- Lead time — default 7 días
- Colchón de seguridad — default 7 días
- Cobertura objetivo — default 30 días

Fórmulas:
- `ROP = vel_reciente * lead_time + vel_reciente * colchon`
- Si `stock_actual <= ROP`: `pedir = max(0, round(vel_reciente * (lead_time + cobertura) - stock_actual))`
- `dias_restantes = stock_actual / vel_reciente` (si vel > 0)
- `dias_quiebre = max(0, lead_time - dias_restantes)`
- `facturacion_en_riesgo = vel_reciente * precio * dias_quiebre`

**Confianza:** "baja confianza" si el producto vendió < 5 unidades **o** en
< 3 días distintos (umbrales configurables). No dispara alerta roja.

## Alertas y UI

- **a)** No es crítico si `pedir == 0`.
- **b)** Productos de baja confianza no disparan alerta; se listan en sección
  colapsada aparte.
- **c)** Lista y tabla ordenadas por `facturacion_en_riesgo` desc. Se elimina la
  columna/score "Urgencia" inventado.
- Se mantiene: KPIs superiores, gráfico de barras de velocidad, evolución por
  producto, export CSV.
- Tabla: nuevas columnas `Vel. histórica`, `Vel. reciente`, `Confianza`,
  `Facturación en riesgo`, `Restock sugerido`, `ROP`, `Días restantes`.
- La solapa **se desacopla del selector de período lateral**: vista histórica usa
  toda la historia; reciente usa su propio slider de N días (default 90).

## Edge cases

- Producto sin ventas o sin stock cargado → no rompe; "sin datos" / "baja confianza".
- Stock "sin límite" (variante sin tope) → nunca crítico.
- Producto multi-variante → stock agregado por nombre.
- Historial vacío (antes del primer snapshot) → todo cae en proxy A.
- División por cero → denominador mínimo 1, guardas `vel > 0`.

## Testing

- Función `calcular_velocidad_restock()` probada con casos sintéticos:
  1. Producto que se quiebra (stock 0 ahora, ventas concentradas) → vel alta.
  2. Producto zombie (vendió hace meses, nada reciente) → vel reciente ≈ 0.
  3. Orden multi-producto con cantidades dispares → conteo correcto vía `Items`.
  4. Tramo con snapshot parcial → híbrido real + proxy.
- Verificación de sintaxis obligatoria antes de commitear:
  `python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read())"`

## Fuera de alcance

- Tarea programada / cron para el snapshot (queda como mejora futura si se
  escapan días).
- Modelo estadístico de stock de seguridad (z·σ·√LT): el volumen de ventas lo
  haría ruidoso; se usa colchón en días.
- Lead time / pack size por proveedor o por producto (perillas globales por ahora).
