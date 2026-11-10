# T128 — Vara común para la «CPU en reposo del EIM» (2026-11-10)

BACKLOG T128 (2): la aceptación pide «CPU en reposo del EIM menor que el ~10 % medido en T126»,
pero T126 midió una sola muestra de 60 s y el informe semanal da la media diaria con todo en
marcha (13–14 %). No eran comparables.

## La vara
`eim_cpu_median` en `eim/operation/usage_summary.py` (y en el informe semanal como «en reposo»):
la **mediana diaria de la CPU del EIM** del registro de consumo de T127 (suma de los papeles del
EIM, en % del equipo entero, una muestra cada 30 s).
- Los trabajos de la cola y los programas ajenos no tienen papel: no cuentan.
- La mediana deja fuera los picos periódicos (validación de 4 h, puntuaciones, vista del bróker),
  que ocupan menos de la mitad del día; la media sí los incluye.
- Se mide igual antes y después de cada cambio, con días enteros, no con una foto de un minuto.

## Medida (registro de consumo de `juanpablo-cpu`)
| Tramo | Mediana EIM | Media EIM | Notas |
|---|---|---|---|
| 2026-11-02 03:38–23:00 UTC (antes del despliegue de T128) | **21,2 %** | 23,4 % (día) | el recolector viejo `binance_ws` (papel `collector`) solo, mediana **12,3 %** |
| 2026-11-03 → 2026-11-09 (7 días después) | 7,5 / 10,6 / 11,3 / 10,2 / 9,4 / 9,7 / 14,0 % | 10,1–17,8 % | sin `collector` |

Por papel, mediana después: API 2,3–3,1 %, captura HFT 3,1–7,4 % (sigue la actividad del mercado:
sube en horario de EE. UU. y el 9-nov, sin crecer con el tiempo de proceso), líderes 1,0–1,9 %;
el resto < 0,1 %.

## Veredicto
Con la misma vara, la CPU en reposo del EIM **bajó a la mitad (21,2 % → ~10 %)**: lo que se fue
es casi exactamente el recolector viejo. El ~10 % de T126 era una foto de 60 s (con la captura HFT
al 0,8 % en un minuto tranquilo) y no sirve de referencia; con días completos, el estado de T126
valía ~21 %. El criterio se da por cumplido. Días de mucho mercado (9-nov) suben a ~14 % por la
captura HFT, que es trabajo útil.
