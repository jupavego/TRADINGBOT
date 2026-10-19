# T72 — Decisiones del observatorio (una página, para revisión del usuario)

Fecha: 2026-10-19 · Equipo de referencia: i5-8250U, 7,9 GB (navegador integrado de la app). Todo lo de abajo está **medido o leído en la fuente**, no tomado de la conversación de chat. Los umbrales viven en `v2/eim/observability/thresholds.py`; cambiarlos exige reabrir esta nota.

## 1. Librería de grafo → **Cytoscape.js (MIT)**
| Candidato | Fuente verificada (npm + `LICENSE` del paquete) | Resultado |
|---|---|---|
| **cytoscape 3.34.4** (15-oct-2026) | MIT, © Cytoscape Consortium | **Elegida.** +138 KB gzip (444 KB min). 60 nodos / 104 aristas: crear 172 ms; layout manual por etapa (`preset`) 18 ms; `breadthfirst` 35 ms; `dagre` 130 ms. Redibujado completo del lienzo 24 ms (p50) / 35 ms (p95), cota superior que incluye codificar PNG. Foco con teclado y flechas que cambian la selección: viable (lo escribe T75; Cytoscape no trae navegación por teclado). |
| cytoscape-dagre 4.0.1 + dagre 0.8.5 | MIT | Opcional: +16 KB gzip. No hace falta: las 7 etapas dan la columna (x) y T75 ordena dentro de cada una. |
| @xyflow/system 0.0.83 | MIT | Descartada: solo ayudas sin interfaz (zoom/trazo de curvas, +20 KB); habría que dibujar nodos a mano. Cytoscape ya sirve. |
| elkjs 0.12.0 | **EPL-2.0 OR GPL-3.0**, 8 MB | Descartada: licencia dual con copyleft y peso, sin necesidad medida. |
Límite honesto: con el panel oculto no se pueden medir cuadros por segundo (el navegador congela la animación); por eso se midió el coste del redibujado. **T75 repite la medición con la vista abierta** antes de cerrar. Instalar: `npm i cytoscape` en `eim/web` (lo hace T75, no esta tarea).

## 2. Descartado por la nota (sin reabrir salvo necesidad medida)
Langfuse, Phoenix (ELv2), Grafana (AGPL-3.0), Prefect, Dagster, Airflow, Temporal, dash-cytoscape, streamlit-agraph, OpenTelemetry: otra pila (Dash/Streamlit/React), otro servidor o Docker, licencia no permisiva, o ya cubierto por el ciclo y el supervisor de T31. De Prefect/Dagster solo se toman los **patrones** (estados de ejecución, linaje de activos).

## 3. El diseño «los procesos escriben archivos, uno indexa» aguanta
`python v2/scripts/obs_bench.py` (reproducible): dos procesos a **1 000 eventos/s cada uno durante 10 s** → 20 000 líneas esperadas, 20 000 válidas, **0 corruptas**, 20 000 ids únicos, 0 descartes, 6,7 MB. Mismo resultado a 2 000 ev/s con los dos procesos en el **mismo archivo** (por eso el nombre lleva el `pid`, aun así). Indexación por **un** proceso en DuckDB: 20 000 filas en **0,35 s**. Contraprueba: dos procesos abriendo la misma base para escribir → el segundo falla (`IOException: Cannot open file`); **no se escribe directo en la base**. Sobre disco real: 335 B por evento.

## 4. Umbrales fijados (antes de construir T73–T76)
| Qué | Valor | Medido |
|---|---|---|
| Coste de `emit()` en el hilo que llama | p95 ≤ **500 µs** | p50 50 µs · p95 148 µs · p99 371 µs |
| Eventos por ciclo | ≤ **100** (lo demás se agrega) | ciclo de agentes ≈ 4,5 s (13 agentes) |
| Sobrecosto máximo del ciclo | ≤ **1 %** del ciclo y ≤ **50 ms** (el menor) | 100 eventos ≈ 3–8 ms (disco roto o sano) |
| Cola por proceso | **10 000**; llena → descarta y cuenta `dropped` | — |
| Retención | spool **7 días**; eventos en la base **30 días**; alerta si el spool pasa de **500 MB** | volumen de diseño ≤ 100 000 eventos/día ≈ 33 MB/día |
| «Sin datos» | sin eventos en **3 × su cadencia** (mínimo **120 s**); a demanda: sin umbral, solo antigüedad | cadencias en el catálogo (`cadence_s`) |
| Mapa (T75) | ≤ **50 ms** redibujado, ≤ **200 KB gzip** añadidos, ≥ **80** nodos | 60 nodos: 24–35 ms · +138 KB |

## 5. Lo que salió y desviaciones
- `eim/observability/`: `events.py` (evento, `trace_for`), `emit.py`, `redact.py`, `thresholds.py`, `catalog/` (76 componentes: 17 agentes + 41 servicios/motores + 18 planeados; todos con etapa, `title_es`, `explain_es`; aristas validadas por origen y artefacto) y glosario. Tests en `tests/observability/`.
- **Desviación:** la spec pedía `catalog.py` **y** `catalog/components.py`; Python no admite módulo y paquete con el mismo nombre, así que `catalog/` es un paquete (`__init__.py` = acceso y `problems()`, `components*.py` = datos).
- **Desviación:** `emit` no se reexporta desde `eim.observability` (taparía al módulo `emit.py`); se importa como `from eim.observability.emit import emit, span`.
- `rejected` se añade a `status` para veto/rechazo (no es un fallo). `mode` acepta `REAL` porque `Mode` lo define, pero nada lo emite.
- Pendiente del usuario: revisar esta página antes de T73–T75 (no bloquea otras tareas).
