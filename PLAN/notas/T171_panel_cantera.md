# T171 — Panel «Cantera»: qué muestra y de dónde sale cada cifra

Modo **SIMULADO**. Diseño: `PLAN/notas/T167_cantera.md` §3 y §7, nota §10 (rec. 8, 15, 17 y 20).

## Contabilidad aparte (petición del usuario, 2026-11-11)

La cabecera de la pestaña lo dice antes que cualquier cifra: el P&L, el saldo, el drawdown y las
operaciones de la cantera son un libro propio (`data/paper_cantera.duckdb`, T168) y **no se suman
nunca** a los cuatro perfiles principales ni a la contabilidad oficial de T144
(`eim/paper/universe.py`). El panel solo lee `GET /v2/nursery`; no hay ningún POST.

## Vista de entrada: la panorámica por agente

`eim/nursery/panel.py::build_panel` (puro) se calcula en cada ciclo de la cantera
(`NurseryDesk.compute`) y viaja en `GET /v2/nursery` como `panel`. Por agente, sus prospectos con:

| Columna | Fuente |
|---|---|
| Etapa y desde cuándo, con el motivo de cada criterio al pasar el puntero | escalafón de T170 (`ladder.py`), solo cambia en las revisiones fijas |
| Rentabilidad neta acumulada %, saldo, drawdown máximo | `summary.account_summary` (cuenta propia, costos y funding incluidos) |
| n, acierto, costo pagado | ídem |
| Frente a sus gemelos al azar | rentabilidad propia − la de sus gemelos (P&L diario de los gemelos) y d medio en R |
| Frente a comprar y mantener | en unidades de riesgo, largo / corto, y el R de la cuenta separado en largo y corto |
| Frente al hermano simple y al `agente_{id}` genérico | diferencia de rentabilidad en las mismas fechas |
| R neto bruto y d̃ bruto / encogido | `themes.shrink` (Bayes empírico hacia su tema, rec. 7–8) |
| Régimen | régimen dominante de sus operaciones y d por régimen al pasar el puntero |
| Señal temprana | volatilidad del R y drawdown frente a su tope calibrado (rec. 17) |
| Días hasta veredicto | MinTRL de T161 (`validation/power.py`) sobre la hipótesis primaria (d̃ recortado a ±3 R, por operación o por día según la banda) con **α = 0,05 / m** (z = 3,09 con m = 50), al ritmo de observaciones de la cuenta |

La cabecera publica las **promesas falsas que espera el azar** tal como las fijó el pre-registro
(`false_promises`: 0,0068 de media, P(≥ 1) = 0,67 %, e-BH con q = 0,10 sobre m = 50), la próxima
revisión, el plazo, el recuento por etapa y la cobertura (alta, días medidos, operaciones cerradas,
último cierre, fuente).

## Honestidad con la muestra

- Orden por defecto: **agente y etapa**, nunca rendimiento. No hay ningún control para ordenar por
  rentabilidad.
- Con menos de 30 observaciones (operaciones, o días en la banda semanal) la cifra se atenúa y
  lleva «muestra insuficiente · n/30».
- «Días hasta veredicto» dice «sin estimación» con menos de 5 observaciones y «no apunta a
  ventaja» con d̃ ≤ 0: no se inventa un plazo que la muestra no da. Si la estimación cae más allá
  del plazo de la fase, lo marca.
- Filtro y agrupación por banda de horizonte (scalping, intradía, tres días, semanal) con la unidad
  de cada una.

## Ficha del prospecto

`GET /v2/nursery/prospect/{id}` (`panel.prospect_card`): su teoría en una frase (expediente de
T167), la regla, las variables que lee con su fuente, los parámetros con su cita, las obras del
catálogo con su postura (respalda / matiza / contradice) y su curva simulada realizada con cada
operación marcada, más la tabla de operaciones (R, d frente a los gemelos y P&L).

## Verificación

- `tests/nursery/test_panel_t171.py`: orden por agente y etapa, cabecera con la contabilidad aparte
  y las promesas falsas, cifras y comparaciones en todos los prospectos, muestra insuficiente,
  MinTRL con α de la familia, ficha y rutas solo de lectura (404 y 405).
- Render comprobado en Chrome con el código compilado (tsc estricto) y un libro sintético: 42 filas
  en 12 agentes, 32 atenuadas, filtro y agrupación por banda, ficha con curva y operaciones.
- En la portátil la cantera está apagada (`EIM_NURSERY=0`, sin `paper_cantera.duckdb`): la pestaña
  lo dice y no inventa nada. La cantera corre en el equipo de Juan Pablo; allí el panel se ve con
  sus datos reales al traer `main` y reiniciar.
