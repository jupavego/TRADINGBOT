# T72 — Universo del centro de observabilidad (insumo, 2026-10-19)

Pedido del usuario (2026-10-19): un **módulo con vista aparte** para ver, en un esquema visual (diagrama o flujo), cómo se comporta y ejecuta el proyecto: qué agente corre, qué datos recibió, qué produjo una señal, dónde falló algo y cómo se llegó a una decisión. Esta nota recoge la investigación inicial (hecha fuera del repo, con el conector de GitHub) **y la contrasta con el proyecto real**. Es insumo de T72; no es una decisión.

## 1. Qué trajo la investigación (sin verificar: T72 lo comprueba todo)
Las cifras de licencia, actividad y versión de Python vienen de una conversación de chat, no de una lectura propia. Hasta que T72 las confirme con el `LICENSE` real, la fecha de la última confirmación y las dependencias, son **hipótesis**.

| Grupo | Candidato | Lo que se dijo | Qué comprobar en T72 |
|---|---|---|---|
| Grafo | `plotly/dash-cytoscape` | MIT, mejor grafo para Dash | **No aplica**: EIM no usa Dash (ver §2). Solo como referencia de diseño. |
| Grafo | `ChrisDelClea/streamlit-agraph` | MIT, prototipo rápido en Streamlit | **No aplica** (EIM no usa Streamlit). |
| Grafo | Cytoscape.js (la librería de fondo) | no evaluado en el chat | Candidato real para la UI actual (TS sin framework). Licencia, tamaño, rendimiento con ~60 nodos. |
| Grafo | `xyflow/xyflow` (React Flow) | «primera opción si hay React» | Requiere React: EIM no lo tiene. Evaluar solo si `@xyflow/system` sirve sin React; si no, descartar. |
| Grafo | elkjs / dagre / d3 | no evaluados | Trazado por capas del grafo estructural. |
| Telemetría | OpenTelemetry (SDK Python + Collector) | Apache-2.0, formato común | ¿Aporta algo en un solo equipo sin Docker? ¿Basta un adaptador de exportación opcional? |
| Trazas IA | Langfuse | MIT en el núcleo, partes con otra licencia; requiere servicio propio | Solo habría llamadas LLM en `context` (T24) y `localai` (T63); ¿justifica un servicio? Esperado: no ahora. |
| Trazas IA | Arize Phoenix | **ELv2** (no permisiva) | Esperado: descartar por licencia y por peso. |
| Orquestación | Prefect, Dagster, Airflow, Temporal | Apache-2.0 (Prefect/Dagster); Temporal por revisar | EIM ya tiene su supervisor, vigilante y ciclo (T31). Estudiar **patrones** (linaje de activos, estados de ejecución), no adoptar el servidor. |
| Métricas | Grafana | **AGPL-3.0** | Esperado: descartar (otro servicio, otra licencia, otra interfaz); series con Lightweight Charts, que ya está. |

## 2. Dónde la investigación no coincide con el proyecto
La investigación asumió «Python/Streamlit/Dash» y «PostgreSQL». El proyecto real es otro, y eso cambia la arquitectura:

| Supuesto del chat | Realidad (verificada en el repo) | Consecuencia |
|---|---|---|
| UI en Streamlit o Dash | UI en **Vite + TypeScript sin framework + Lightweight Charts** (`v2/eim/web/package.json`); vistas de pantalla completa por botón (`main.ts`, p. ej. «Bróker simulado») | El grafo va en TS; la «vista aparte» sigue el patrón de `paper_view.ts`. No hay biblioteca Python de grafos que valga. |
| PostgreSQL como registro maestro | Todo el almacén es **DuckDB + Parquet**, local, sin servidor; T62 ya descartó PostgreSQL por la misma razón | Registro propio en DuckDB (`obs.duckdb`). |
| Varios procesos escriben a la misma base | **DuckDB admite un proceso escritor por archivo** (ya obligó a un servicio de líderes aparte, `OPERACION.md` §6) | Los procesos **no** escriben en la base: emiten eventos a archivos JSONL por proceso (sin cerrojo) y **un solo indexador** los carga. Mismo patrón que `heartbeat.json` y el registro JSONL de alertas. |
| Instrumentar cada agente | Regla de `CLAUDE.md`: los agentes son **funciones puras, sin I/O ni estado global** | La instrumentación vive en el **corredor** (`agents/runner.py`), el ciclo y los servicios; **el código de los agentes no se toca** y sus reportes quedan idénticos bit a bit. |
| Telemetría de «scripts independientes» | Hay un flujo central (agentes → síntesis → plan → riesgo → puerta única) más servicios aparte (operación, líderes, recolector, bróker simulado, calendario, copias) | Dos grafos: **estructural** (lo declarado en el catálogo) y **de ejecución** (lo que de verdad pasó, por decisión). Las diferencias entre ambos se muestran. |
| Correlación por `trace_id` compartido | Los procesos no comparten memoria | `trace_id` **determinista** = (símbolo, marco, cierre de vela): todos los procesos que trabajan sobre la misma vela caen en la misma traza sin coordinarse. |

## 3. Lo que ya existe y se reutiliza (no se duplica)
`data/operation/heartbeat.json` y alertas `op_alerts` + JSONL por día (T31) · `RiskDecision` sellada y `risk_decisions` (T29) · `reports`/`forecasts` y el replay `as-of` (T8, T15, T17) · `Report` de cada agente con `status`/`warnings` (T5) · `sim_trades` (T15) · `val_*` (T49) · copias (T32) · cola y estados de video (T64, cuando exista). El observatorio **lee y enlaza** estas fuentes; no crea un segundo sistema de alertas ni un segundo libro de operaciones.

## 4. Principios de diseño (aplican a T72–T76)
1. **Observar no es operar.** El módulo es de solo lectura sobre dinero y posiciones. Las acciones de control quedaron fuera de la fase (BACKLOG); si algún día se añaden, pasarán por servicios con permiso, auditoría y límites, nunca como efecto lateral de un clic.
2. **Nunca romper el sistema que observa.** Emitir un evento no puede lanzar excepción, bloquear ni demorar el ciclo; si falla se descarta y se cuenta. Presupuesto de sobrecosto medido.
3. **Sin telemetría ≠ sano.** Un componente sin eventos recientes se pinta «sin datos», nunca verde. Cada estado muestra su fuente y su antigüedad (regla del proyecto: ninguna cifra sin `source` y cobertura).
4. **Tres hechos distintos:** una señal calculada, una decisión aprobada y una orden enviada son eventos separados, con identificadores propios, y así se dibujan.
5. **Referencias, no copias.** Los eventos llevan hashes e identificadores de entradas/salidas (snapshot, reporte, versión de parámetros), no volcados de mercado. Nunca claves, tokens ni cabeceras.
6. **Local y sin servicios nuevos** salvo que T72 demuestre lo contrario con medición; sin Docker; sin enviar telemetría a terceros.
7. **Los módulos futuros se registran al nacer** (Fase 14: `localai`, cadena de video; Fase 12: bots): el catálogo es parte del checklist de «agente/servicio nuevo» (T72 actualiza `docs/NUEVO_AGENTE.md` y la skill `eim-new-agent`).

## 5. Mapa de tareas (Fase 15)
Recortado el 2026-10-19 de 8 a 5 tareas (sin auditoría exhaustiva ni control autónomo): T72 decide la librería de grafo con una medición corta y fija contrato + catálogo + emisor → T73 indexador/almacén/API ‖ T74 instrumentación de lo existente → **T75 mapa visual del flujo de trabajo (vista central, pedagógica)** → T76 relato de una decisión, camino causal y calidad de la evidencia.
- **Pedagógico:** la vista debe poder leerla quien no programa (pedido del usuario): lenguaje llano, leyenda, recorrido guiado, animación solo con datos reales, módulos planeados en punteado.
