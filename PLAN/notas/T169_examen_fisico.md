# T169 — Examen físico: hallazgos (2026-11-16)

Informe: `v2/reports/t169_examen_fisico.md` (+ `.json`). Plan y umbrales, fijados antes de correr:
`PLAN/T169.md`. Modo **SIMULADO** y **sin rendimiento**: aquí no hay R neto, acierto ni PF.

## Resultado

| | Prospectos |
|---|--:|
| Con historia, examinados | 32 de 43 |
| Descartados por razones mecánicas | 16 |
| Siguen | 16 |
| … de ellos «sin opción a primer equipo» (< 100 operaciones esperadas en 6 meses) | 4 |
| Sin historia (se examinan hacia adelante) | 11 |

- **Siguen con opción:** `vwap_tendencia`, `niveles_rebote`, `tec_ruptura_volumen`, `pa_patron_zona`,
  `lit_consenso`, `lit_nison_giro`, `niveles_canal_extremos`, `estructura_retroceso`, `pa_choch`,
  `pa_bos`, `pa_bos_patron` y `niveles_ruptura`. Van ordenados por días hasta el veredicto.
- **Los más rápidos en llegar a un veredicto**, con μ = +0,10 R y α = 0,05:

  | Prospecto | Días |
  |---|--:|
  | `vwap_tendencia` | 76 |
  | `niveles_rebote` | 92 |
  | `tec_ruptura_volumen` | 101 |
  | `pa_patron_zona` | 126 |

  Con la corrección de la familia (z ≈ 3,09), ninguno llega en 6 meses si μ = +0,10 R. Con μ = +0,25 R llegan 7.
- **Sin opción a primer equipo:** `ema_elastico`, `lit_murphy_rsi`, `estructura_continuacion` y
  `vwap_semanal`.
- **Comprobaciones limpias:**
  - Identidad del subconjunto: 9 de 9 contextos con `nat` idéntico al de la mesa completa.
  - No anticipación: 18 cortes, con 162 contextos recalculados sobre el banco truncado. Hubo 0 diferencias en contextos y en ideas.
- **Costo:** 3,5 h de cálculo, 3,6 h de reloj con 4 pausas de la cola y RAM ≤ 135 MB. El plan preveía unas 6,4 h.

## Cuatro reglas que no se cumplen nunca

No es mala suerte de la muestra. Por cómo emite cada agente, la regla **no puede** cumplirse:

1. **`elliott_onda3` y `elliott_onda5_giro`.** `eim/agents/elliott/compute.py:66` asigna las
   etiquetas `0…C` por posición a los últimos pivotes, así que `pivots[-1].wave_label` es siempre
   `C`, en los 7 876 contextos de 4 h. Las reglas esperan `2` o `5` en el último pivote y nunca lo ven.
2. **`estructura_ruptura`.** El escenario SC-02 (ruptura) aparece en 775 contextos de 1 h, con 524
   transiciones. Pero el agente le da una convicción de 47 a 50 (mediana 47), y la regla pide
   `conviction_min` = 60, un valor provisional de la banda SR-2 que no está calibrado.
3. **`tec_acuerdo_marcos`.** Con base 1 h, el agente `technical` solo evalúa los marcos vecinos
   (15 m y 4 h), así que `frames.1d.bias` no existe nunca a 1 h. **Tampoco existe en vivo**: no es
   un hueco del banco, y la mesa completa también lo da vacío (comprobación de identidad).

Rediseñarlas no le toca a T169 (BACKLOG): la nota de T167 permite cambiar una regla solo antes del
pre-registro (T170).

## Gemelos físicos

**`regimen_tramo_estable` = `regimen_tramo`**: tienen las mismas ideas y las mismas operaciones,
porque `metrics.unstable` es falso en los 10 752 contextos de 1 h. Así, el filtro «estable» no filtra
nada en la historia. Para T170, los dos cuentan como un solo prospecto.

## La banda que mide la tenencia no es la declarada

19 de los 32 prospectos cambian de banda. Manda la banda medida, como se fijó en `PLAN/T169.md`.
El informe muestra, para cada descarte, si con la banda declarada seguiría vivo, y **5 descartes
dependen de esa reasignación**:

| Prospecto | Banda declarada | Banda medida |
|---|---|---|
| `ema_pila` | semanal | tres días |
| `lit_regla_4_semanas` | semanal | tres días |
| `vwap_anclado` | semanal | tres días |
| `ema_retroceso` | intradía | scalping |
| `tec_compresion_bb` | intradía | scalping |

El patrón viene de la plantilla de salida, no de las reglas:

- **`atr_ladder` en 1 h:** los 7 prospectos de 1 h con esta plantilla que operan tienen
  tenencias medianas de 1,25 a 1,6 h, con el cuartil 75 en 2,75–3,75 h. Todos pasan de intradía a
  scalping. No se investigó qué escalón cierra antes.
- **`rule_flip` en 4 h:** los 6 prospectos de 4 h declarados semanales que operan tienen
  tenencias medianas de 4 a 62 h. Todos pasan a intradía o a tres días.

La nota de T167 deducía la banda de la plantilla y del marco. **Medida, esa deducción no se
cumple.** Para T170 hay dos salidas: declarar la banda medida o cambiar la plantilla antes del
pre-registro.

## Otras observaciones

- **Literatura:** `metrics.hits[]` tiene algún elemento en solo el 7–11 % de los contextos. Es una
  lista vacía, no un dato perdido: ninguna ficha acierta en esa vela.
- **Canales:** `metrics.channel` falta en el 8–10 % de los contextos de `levels`, que es cuando no
  hay canal.
- **Costo:** solo `vwap_reversion` (15 m) cae por costo, con 0,337 R por encima del tope de 0,3 R.
  `lit_regla_4_semanas` queda al borde de costo.

## Limitaciones

- La σ de 1 R por operación es **supuesta**: medirla exigiría calcular R en la historia, y T169 no
  lo hace. Los días hasta el veredicto escalan con σ².
- Las reglas que miran contextos anteriores (transiciones) no deciden en el primer contexto de
  cada bloque de 28 días.
- La muestra de 1 h y 15 m son 16 bloques de 28 días, uno de cada tres. Los demás bloques
  (k ≡ 1, 2 mód 3) quedan libres si hace falta ampliarla.
