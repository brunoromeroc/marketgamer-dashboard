# Claude Code — Market Gamer Dashboard

## Contexto del proyecto
- Dashboard Streamlit para Market Gamer (consolas retro, Argentina)
- Integra: TN API (store 6623036), Google Sheets (CostosConsolas, Proveedores, SaludFinanciera)
- archivo principal: app.py (~2500 líneas)
- Exchange rate: SIEMPRE dólar blue, nunca oficial
- Precios: SIEMPRE precio unitario de TN API, NUNCA dividir total por cantidad
- Margen confiable: Tab 3 (Salud Financiera), no Tab 1
- UI: español argentino con voseo

## Flujo para mejorar el dashboard

### Mejora chica (fix, ajuste visual, dato nuevo)
1. /programar — leer todo ? plan ? implementar ? verificar
2. /smart-commit — commit con mensaje descriptivo
3. git push

### Mejora grande (feature nueva, sección nueva, rediseño)
1. /understand — analizar el proyecto completo
2. /brainstorming — diseñar la mejora, genera spec en docs/superpowers/specs/
3. /writing-plans — convierte spec en pasos de 2-5 min
4. /executing-plans — Claude ejecuta los pasos
5. /verification-before-completion — chequeo antes de cerrar
6. /smart-commit — commit limpio
7. git push
8. /wrap-up — documentar estado en .superclaudio/estado.md

### Cuando algo se rompe
1. /systematic-debugging — causa raíz obligatoria antes de tocar código
2. /programar — fix
3. /smart-commit

### Al arrancar una sesión
1. Leer .superclaudio/estado.md — ver dónde quedó
2. Si existe .understand-anything/knowledge-graph.json ? sugerir /replay-learnings
3. Elegir flujo según el tipo de tarea

## Agentes disponibles

### Para tareas paralelas grandes (agent-teams)
Cuando hay múltiples cambios que no se pisan entre sí.
- Activar con: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
- Tamaño útil: 2-3 teammates para este proyecto
- Usar SOLO si las tareas tocan secciones distintas del dashboard
- NO usar para fixes o cambios en las mismas líneas

### Para exploración rápida (subagent)
Cuando querés que Claude investigue algo sin tocar el código principal.
- "Usá un subagente para analizar cómo está estructurada la tab de Proveedores"

## Reglas del proyecto
- NUNCA commitear .streamlit/secrets.toml
- SIEMPRE verificar sintaxis antes de commitear: python -c "import ast; ast.parse(open('app.py').read())"
- Dólar blue: fetchear de la API, nunca hardcodear
- Pendiente: completar sección GCP Service Account si falla Google Sheets
