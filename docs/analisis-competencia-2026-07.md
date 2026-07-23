# Análisis de competencia y márgenes — 23/07/2026

Relevamiento hecho con 5 agentes en paralelo (MercadoLibre vía JSON-LD/snippets, tiendas
argentinas en vivo) + costos de CostosConsolas + dólar blue $1.560. Margen teórico según
fórmula del dashboard (comisión 4,15% + IVA 10,5% + packaging $2.500).

## Semáforo de posicionamiento

| Producto | Precio MG | Mercado (activo) | Posición | Mg teór. | Acción sugerida |
|---|---:|---|---|---:|---|
| R36S | $140.000 | $80–140k, med ~$90k | 🔴 muy caro | 36% | Repensar: commodity, ML lo vende al costo |
| Anbernic RG 35XX | $170.000 | $123–151k, med ~$140k | 🔴 caro y margen flaco | 23% | Liquidar/discontinuar → empujar 35XXSP |
| Retroid Pocket 4 | $600.000 | $399–511k (Retro Store) | 🔴 caro | 40% | Bajar a ~$500k |
| Retroid Pocket G2 | $1.100.000 | $715k (Onitech, stock ya) | 🔴 muy caro | 50% | Bajar a ~$750–800k |
| Anbernic RG 35XXSP | $215.000 | $154–198k | 🟡 algo caro | 41% | Mantener o -5% si no rota |
| Trimui Smart Pro | $240.000 | $195–237k | 🟡 leve caro | 32% | Mantener |
| Miyoo Mini Plus | $160.000 | $144–195k, med $160k | 🟢 alineado | 28% | Mantener (producto de volumen) |
| Anbernic RG 406V | $540.000 | $495–640k, med $565k | 🟢 alineado | 28% | Mantener (ojo transf. rivales ~$478k) |
| Trimui Brick | $230.000 | $220–250k | 🟢 alineado | 37% | Mantener |
| Powkiddy X55 | $350.000 | $328–355k | 🟢 alineado | 48% | Mantener |
| Anbernic RG 557 | $950.000 | $927k (TeraTech) | 🟢 alineado | 35% | Mantener |
| AYN Odin 3 | $1.200.000 | $899k (60 días)–$1.199k | 🟢 techo c/stock | 36% | Mantener, vender "entrega inmediata" |
| Powkiddy RGB30 | $200.000 | $199–287k | 🔵 barato | 31% | Subir a ~$220k |
| Anbernic RG 34XXSP | $240.000 | $211k import–$360k ML | 🔵 barato | 36% | Subir a ~$270–280k |
| Anbernic RG CUBE XX | $250.000 | $227–310k, med $265k | 🔵 barato | 31% | Subir a ~$270k |
| Trimui Smart Pro S | $300.000 | $319–399k (solo TeraTech) | 🔵 barato | 39% | Subir a ~$330k |
| Anbernic RG VITA PRO | $600.000 | único vendedor local | ⭐ solo | 41% | Subir a ~$650k |
| Anbernic RG 476 H | $550.000 | sin oferta local | ⭐ solo | 32% | Subir a ~$590–600k |
| Miyoo A30 | $159.000 | sin oferta local activa | ⭐ solo | 40% | Subir a ~$175k |
| Miyoo Mini Flip | $200.000 | sin oferta local activa | ⭐ solo | 42% | Mantener o subir leve |
| Miyoo Flip V2 | $240.000 | sin activa (dato viejo $198–237k) | ⭐ solo | 37% | Subir a ~$260k |
| Anbernic RG 40XX V | $240.000 | escaso (import $198k) | ⭐ casi solo | 37% | Mantener |

Piso (margen 0) por producto: ver script `piso.py` de la sesión — regla rápida:
piso ≈ (costo_total_usd × blue + 2500) / 0,8535.

## Competidores especialistas reales

- **OniTech** (onitech.com.ar, Tienda Nube): pelea peso a peso en Anbernic, entrega <24 hs,
  10% off transferencia. Tiene la Retroid G2 a $715k.
- **TeraTech** (teratech.com.ar, WooCommerce): el más agresivo — "importador directo",
  20% off transferencia, pero demoras de entrega (review: 41 días). Solapa mucho catálogo.
- **Retro Store** (retrostore.com.ar): premium AYN/Retroid + Discord + usadas. Retroid P4
  a $399–511k. Productos a pedido (60 días).
- Retro Port domina clones baratos (R36S). Estado Gamer y FG Store generalistas con ítems sueltos.
- **Tienda Rocket suspendida** (era #1 en Google para "consolas de juegos portátiles") →
  oportunidad SEO inmediata.

## Hallazgos estructurales

1. **Patrón de pago del mercado**: 10–25% descuento por transferencia es estándar en todos
   los competidores. MG no lo comunica → palanca de margen (transferencia = sin comisión).
2. **Brecha real vs teórico**: margen real (25,3% pond.) da 5–8 pp abajo del teórico —
   costo de cuotas/descuentos/envíos. Medirla exacta requiere margen en USD por fecha.
3. **SEO**: MG rankea #1–2 en las búsquedas clave (miyoo, retroid, powkiddy, anbernic AR).
   IG 6,5k seguidores vs Nakama 62k (pero Nakama es retro de colección, no handhelds).
4. **MercadoLibre**: ~25 tiendas oficiales en el filtro de Anbernic; bloquea scraping.
   Los precios ML capturados vienen de JSON-LD de catálogo.

## Próximos pasos acordados (pendientes de implementación)

1. Margen histórico "verdadero" en USD por fecha de venta (serie blue de Bluelytics).
2. KPI margen ponderado + objetivo + tendencia en solapa Dashboard.
3. Precio piso + semáforo competencia en solapa Precios.
