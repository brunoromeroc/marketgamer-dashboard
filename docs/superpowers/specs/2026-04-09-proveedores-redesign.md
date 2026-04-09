# Proveedores Tab — Rediseño completo

**Fecha:** 2026-04-09  
**Archivo afectado:** `app.py` (tab10 únicamente)  
**Nueva dependencia:** `python-pptx`

---

## Contexto

La solapa de Proveedores existe pero tiene tres problemas concretos:

1. **No hay forma de actualizar precios** — cuando llega una lista nueva hay que borrar y recargar todo a mano sin ver qué cambió.
2. **Comparación cross-proveedor limitada** — el pivot table solo funciona si los nombres son idénticos entre proveedores.
3. **No hay herramienta de decisión de compra** — el flujo real de Bruno es: ver stock → comparar precios → armar pedido por proveedor. Hoy eso pasa fuera del dashboard.

Proveedores activos:
- **Anne** (Qbuy Technology) — listas en PDF
- **Linda** (Powkiddy / Trimui) — listas en PowerPoint
- **Winnie** (Anbernic) — listas en PDF, cotizaciones puntuales por WhatsApp

---

## Diseño

El tab mantiene su lugar (tab10). Las 3 vistas con radio button se reemplazan por **3 secciones siempre visibles** en orden vertical.

### Sección 1 — Catálogos

El usuario ve sus proveedores con fecha de última actualización de cada catálogo.

Al subir una lista nueva (PDF, PPTX o CSV/Excel), el sistema muestra un **diff de precios** antes de guardar:
- 🟡 Precio cambiado (producto existente, precio distinto)
- 🟢 Producto nuevo (no estaba antes)
- 🔴 Producto eliminado (estaba antes, ya no está en la nueva lista)

El usuario confirma y el catálogo se reemplaza completo. Se guarda la fecha de actualización.

**Formatos soportados:**
- CSV / Excel — ya funciona, se mantiene
- PDF — pdfplumber, con advertencia de fidelidad baja en catálogos de diseño
- PowerPoint (.pptx) — nuevo, via `python-pptx`. Extrae tablas y texto de cada slide.

**Cambio en data model (GSheets hoja `Proveedores`):**
Se agrega `updated_at` por proveedor (string ISO date). Compatible hacia atrás — si no existe se muestra "Sin fecha".

```json
{
  "suppliers": {
    "Anne - Qbuy Technology": {
      "contacto": "...",
      "web": "...",
      "updated_at": "2026-04-09",
      "productos": {
        "RG40XX": { "precio_usd": 45, "marca": "Anbernic", "screen": "...", "cpu": "...", "battery": "...", "storage": "..." }
      }
    }
  }
}
```

### Sección 2 — Comparador de precios

Tabla unificada con todos los productos de todos los proveedores. Columnas: Producto + un precio por proveedor. La celda más barata de cada fila se marca con ✅.

**Fuzzy matching de nombres:** usa `difflib.SequenceMatcher` (stdlib, sin dependencia nueva). Umbral de similitud: 0.80. Si dos nombres de distintos proveedores superan el umbral, se agrupan como el mismo producto. Si la similitud está entre 0.65 y 0.80, se muestra como "posible coincidencia" con opción de confirmar o descartar manualmente. Las confirmaciones manuales se guardan en sesión.

Filtro de búsqueda por nombre encima de la tabla.

### Sección 3 — Planificador de compra

Cruza stock actual de TN (via `cargar_stock`, que ya existe) con precios del catálogo de proveedores.

**Tabla de productos:**

| Producto | Stock actual | Urgencia | Mejor precio (USD) | Proveedor |
|---|---|---|---|---|
| RG40XX | 1 | 🔴 Crítico | $45 | Anne |
| RG35XX | 3 | 🟡 Bajo | $36 | Winnie |

Urgencia calculada igual que la solapa Velocidad de ventas (ya existe esa lógica).

El usuario:
1. Tilda los productos a reponer
2. Ingresa cantidad para cada uno
3. Puede cambiar el proveedor si quiere (override del sugerido)

El dashboard genera un **resumen de pedido** agrupado por proveedor con total en USD:

```
Pedido a Anne — Total: $225 USD
  · 5× RG40XX × $45

Pedido a Winnie — Total: $108 USD
  · 3× RG35XX × $36
```

Botón "📋 Copiar" para mandar por WhatsApp.

---

## Lo que NO cambia

- Hojas `CostosConsolas` y `SaludFinanciera` en GSheets — sin tocar
- Los demás tabs del dashboard — sin tocar
- La lógica de FOB en márgenes (`get_fob_usd`, `get_costo_total_usd`) — sin tocar
- El catálogo de proveedores NO reemplaza `CostosConsolas`; son herramientas separadas

---

## Dependencias nuevas

| Paquete | Para qué | Agregar a requirements.txt |
|---|---|---|
| `python-pptx` | Parsear PowerPoint de Linda (Powkiddy/Trimui) | ✅ sí |

`difflib` — ya viene con Python, no hay que agregar nada.

---

## Criterios de éxito

1. Bruno puede subir una lista nueva de Anne y ver exactamente qué precios cambiaron antes de confirmar
2. La tabla comparadora muestra los 3 proveedores cruzados aunque los nombres no sean idénticos
3. El planificador genera un resumen de pedido listo para copiar y mandar por WhatsApp
