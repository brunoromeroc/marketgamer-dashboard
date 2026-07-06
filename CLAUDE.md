# Claude Code � Market Gamer Dashboard

## Contexto del proyecto
- Dashboard Streamlit para Market Gamer (consolas retro, Argentina)
- Integra: TN API (store 6623036), Google Sheets (CostosConsolas, GastosFijos, OrdenesEfectivo, HistorialStock)
- archivo principal: app.py (~6600 lineas)
- Exchange rate: SIEMPRE dolar blue, nunca oficial
- Precios: SIEMPRE precio unitario de TN API, NUNCA dividir total por cantidad
- Resultado/margen del periodo: SIEMPRE via calcular_resultado_periodo() — fuente
  unica de verdad que consumen Dashboard, Salud Financiera y Analista IA.
  NUNCA copiar la formula de margen inline en una solapa.
- Config financiera (dolar, IVA, pauta, packaging): global en sidebar, auto-aplicada.
  Leer de session_state (tipo_cambio_sf, pct_iva, pauta_manual, packaging_global).
- UI: espanol argentino con voseo

## Flujo para mejorar el dashboard

### Mejora chica (fix, ajuste visual, dato nuevo)
1. /programar � leer todo ? plan ? implementar ? verificar
2. /smart-commit � commit con mensaje descriptivo
3. git push

### Mejora grande (feature nueva, secci�n nueva, redise�o)
1. /understand � analizar el proyecto completo
2. /brainstorming � dise�ar la mejora, genera spec en docs/superpowers/specs/
3. /writing-plans � convierte spec en pasos de 2-5 min
4. /executing-plans � Claude ejecuta los pasos
5. /verification-before-completion � chequeo antes de cerrar
6. /smart-commit � commit limpio
7. git push
8. /wrap-up � documentar estado en .superclaudio/estado.md

### Cuando algo se rompe
1. /systematic-debugging � causa ra�z obligatoria antes de tocar c�digo
2. /programar � fix
3. /smart-commit

### Al arrancar una sesi�n
1. Leer .superclaudio/estado.md � ver d�nde qued�
2. Si existe .understand-anything/knowledge-graph.json ? sugerir /replay-learnings
3. Elegir flujo seg�n el tipo de tarea

## Agentes disponibles

### Para tareas paralelas grandes (agent-teams)
Cuando hay m�ltiples cambios que no se pisan entre s�.
- Activar con: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
- Tama�o �til: 2-3 teammates para este proyecto
- Usar SOLO si las tareas tocan secciones distintas del dashboard
- NO usar para fixes o cambios en las mismas l�neas

### Para exploraci�n r�pida (subagent)
Cuando quer�s que Claude investigue algo sin tocar el c�digo principal.
- "Us� un subagente para analizar c�mo est� estructurada la tab de Proveedores"

## Reglas del proyecto
- NUNCA commitear .streamlit/secrets.toml
- SIEMPRE verificar sintaxis antes de commitear: python -c "import ast; ast.parse(open('app.py').read())"
- D�lar blue: fetchear de la API, nunca hardcodear
- Pendiente: completar secci�n GCP Service Account si falla Google Sheets
