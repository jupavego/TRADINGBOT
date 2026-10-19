# T54 — Preregistro (2026-10-19)

Fijado **antes de cualquier cálculo sobre datos reales** y de escribir el código de T54. Cambiar algo de aquí después de ver un resultado = documento nuevo (`T54_preregistro_v2.md`) y nueva versión de lo afectado; este archivo no se reescribe. Si ninguna regla pasa y el ajuste queda apagado, ese es el resultado y se informa tal cual.

Datos de partida (lo que se sabe hoy, sin haber mirado nada de T54): T49 declaró «ninguna estrategia validada» (87 intentos: 54 EN OBSERVACIÓN, 33 RECHAZADA); en 1 h las 26 versiones con ≥ 100 operaciones fuera de muestra tienen R medio neto negativo. Lo esperable a priori para reglas de libro sobre BTC es lo mismo; no se preseleccionó mirando resultados.

## A. Reglas elegidas (7 fichas → 5 estrategias de la familia `literatura`)

Criterio de elección, en el orden de `T52_bibliografia.md`: 1.º lo que el autor respalda con cifras o citas empíricas; 2.º lo que tiene evidencia académica citada; 3.º reglas de patrón con SL natural dado por el autor. Se eligen 7 de las 9 fichas codificadas en T53 (límite del plan: ≤ 8), agrupadas en 5 estrategias (pares espejo alcista/bajista) para no gastar intentos de Holm.

| Estrategia (`id`) | Fichas | Respaldo | Marcos |
|---|---|---|---|
| `lit_canal_4sem` | `murphy_weekly_rule` (Murphy 1999, cap. 9, pp. 256–258) | **Cifras**: Dunn & Hargitt (1970), Lukac et al. (1975–84: 4 de 12 sistemas rentables, 2 de canal), Lukac y Brorsen (1990); afín a Brock, Lakonishok y LeBaron (1992) | solo 4 h (*) |
| `lit_rsi_recruce` | `murphy_rsi` (cap. 10, pp. 281–283, 285–286) | Wilder (1978), citado; experiencia del autor | 1 h y 4 h |
| `lit_envolvente` | `nison_engulfing` (Nison 2001, cap. 4, pp. 53–54) | Anecdótica; es el patrón de giro con más refuerzos explícitos | 1 h y 4 h |
| `lit_vela_cola` | `nison_hammer` (cap. 4, pp. 45–46, 48–49) + `nison_shooting_star` (cap. 5, pp. 84–86) | Anecdótica; el autor da la invalidación (mínimo del martillo = soporte; cierre sobre el máximo de la estrella anula) | 1 h y 4 h |
| `lit_estrella_3v` | `nison_morning_star` (cap. 5, pp. 72–73) + `nison_evening_star` (pp. 76–77) | Anecdótica; el autor da el soporte/resistencia (mín./máx. del patrón) | 1 h y 4 h |

Descartadas: `nison_three_white_soldiers` y `nison_three_black_crows` (el autor mismo dice que la señal llega tarde, que son de precios altos/diario y que en 15 m puede ser ruido; la de «bloque de avance» pide no operar). Se pueden añadir después de un veredicto, con versión nueva.

(*) **Hallazgo previo al cálculo**: los contextos de 1 h se generan con 500 velas (`AGENT_BARS`) y la regla de 4 semanas exige 673 velas en 1 h (28 días × 24): en 1 h el agente nunca la evalúa (`rules_evaluated` la excluye y avisa). No se cambia `AGENT_BARS` (movería a todos los agentes). Por eso la estrategia solo corre en 4 h (169 velas necesarias).

Todas solo en **1 h y 4 h**: en 15 m el costo medio fue 0,48 R por operación (T48b), V6 la rechazaría de antemano y cada marco extra gasta un intento de Holm. Total de intentos nuevos: 1 × 1 + 4 × 2 = **9 versiones** (`estrategia@marco`). Cada una endurece la Holm de las 87 existentes (de 87 a 96 intentos): es el costo declarado de añadirlas.

### Entrada, salida y mecánica (fijas; no se retocan tras ver resultados)
- Entrada **a mercado** al cierre de la vela que cumple la regla (`ctx["close"]`); una operación por estrategia@marco a la vez (la sombra de T47); mecánica `ExecParams` por defecto (costos regulares de Binance, break-even+ en 1 h/4 h, `min_risk_frac`).
- `lit_vela_cola`, `lit_estrella_3v`: **SL derivado del patrón**, a 0,25 ATR más allá del extremo (mínimo de la vela/del patrón para largos, máximo para cortos), válido solo si su distancia a la entrada está entre 0,5 y 3 ATR (misma regla que `ind_supertrend`); **TP = 2 R**. Si la distancia no es válida: SL 1,5 ATR y TP 2,5 ATR (los de la mesa).
- `lit_envolvente`, `lit_rsi_recruce`, `lit_canal_4sem`: el autor no da una distancia utilizable en la mesa (en el canal la salida es por ruptura contraria de 1–2 semanas, que la sombra no modela) → SL 1,5 ATR, TP 2,5 ATR, y se anota como desviación de la ficha.
- Tiempo máximo con la posición abierta: 36 (horas de 1 h, escalado al marco). Confianza = fuerza de la regla.
- No entran en los perfiles (`families` no incluye `literatura`): no se tocan los libros ya en marcha; llegan a «Operaciones sugeridas» solo por el camino de T50 y solo si salen **VALIDADAS**.

### Ventanas de ajuste (T49) de las 9 versiones
Las reglas salen de los libros, no de datos. Lo único mirado: T53 verificó las reglas sobre `tests/fixtures/ethusdt_1h_1000.csv` (ETHUSDT 1 h, 2026-05-18 13:00 a 2026-06-29 04:00 UTC). Se declara esa ventana **solo para ETHUSDT**; para BTCUSDT no se declara ninguna (nada de BTC se miró). Origen `T54` en `eim/validation/lineage.json`, añadido en el mismo commit que el código (la declaración no cambia ningún criterio).

### Criterios
Los de `validation_v1` (T49), sin tocar. Informe por regla: lo que afirma el autor frente a lo observado en BTCUSDT (n, R medio neto con IC95 %, acierto, veredicto, y por ficha dentro de cada par espejo).

## B. Ajuste de las probabilidades de escenario

**Forma** (una sola hipótesis, un solo `k`; sin rejilla ni elegir `k` con datos):

p'ᵢ = pᵢ · exp(k · netoᵢ) / Σⱼ pⱼ · exp(k · netoⱼ),  con **k = 0,5**

`netoᵢ` = `scenario_support[i].net` del agente `literature` (−1..+1) calculado solo con velas ≤ origen. `neto = 0` deja las probabilidades igual. No hay ventana de ajuste (k fijo): toda la historia evaluada es fuera de muestra respecto del ajuste.

**Muestra**: BTCUSDT 1 h, pronósticos de `forecast/backfill.py` con el motor base (sin deriva externa ni plan, la línea base de T19), horizonte 25 velas, 200 trayectorias, contexto de 1.500 velas, origen cada 25 velas (**sin solape**: cada ventana de horizonte es disjunta), sobre todo el historial disponible en el almacén al calcular (se anota su inicio y su fin). El agente `literature` ve las **500 últimas velas** del origen (igual que en vivo y en los contextos del bróker), con parámetros por defecto. Etiqueta de resultado = la de `calibration.evaluate_forecast` (T19).

**Criterio de aceptación** (se cumplen TODOS o el ajuste queda apagado):
1. Muestra: ≥ 300 pronósticos evaluados y ≥ 100 con `neto ≠ 0` para algún escenario (si no, «sin evidencia suficiente»).
2. Brier multiclase: media de (Brier base − Brier ajustado) > 0 con IC95 % bootstrap por bloques de día UTC del origen (≥ 5.000 remuestreos, percentiles) cuyo extremo inferior > 0.
3. Log-loss: media de (log-loss base − ajustado) > 0 con el mismo IC y extremo inferior > 0.
4. Calibración: el error de calibración esperado (`ece`) del ajustado ≤ el del base.
5. Cobertura de bandas 50/80/90 % **sin empeorar** (el ajuste no toca las bandas: debe ser idéntica; se verifica).
6. Consistencia: la diferencia media de Brier es > 0 en las dos mitades cronológicas de la muestra.

Si pasa, se activa solo con un commit que pone `enabled: true` en `eim/forecast/versions/lit_tilt_v1.json` (el archivo se crea apagado, con `k` y estos criterios); cambiar `k` o un criterio = `lit_tilt_v2`. Mientras esté apagado, nada cambia en las probabilidades. Cuando esté encendido, el pronóstico lo declara (`ForecastSet.adjustments`, aditivo) y la UI marca «incluye ajuste bibliográfico».

Limitación declarada: el ajuste se mide sobre el motor base (como T19); en vivo la proyección lleva además la deriva de la síntesis. La evidencia es de la línea base, no del pronóstico en vivo.

## C. Contexto del bróker
`paper/context.py` guarda en cada vela `lit` = aciertos compactos `[ficha, dirección, fuerza]` + neto por escenario + versión del agente (`ctx["lit"]`, `CTX_VERSION` 2). Los contextos ya guardados (sin `lit`) se completan **sin regenerar los agentes**: el agente `literature` es puro, se recalcula sobre las velas ≤ `asof` y se fusiona (`python -m eim.literature ctx`). Historia walk-forward en 1 h y 4 h sobre todo el almacén de BTCUSDT. Los agentes no entran en la huella de versión (BACKLOG T49 (4)): la versión de contexto se declara en el informe.

## D. Lo que NO se hará
Retocar umbrales, reglas o `k` hasta que pasen; cambiar `validation_v1`; operar dinero real o testnet. Un ciclo de mejora, si el usuario lo pide tras el veredicto, es versión nueva con ventanas de ajuste declaradas.

## Anexo de implementación (2026-10-19, antes de cualquier cálculo con datos reales)
Detalles que el texto de arriba dejaba a la implementación; no cambian ninguna regla, umbral ni criterio:
- **Log-loss**: −ln(max(p de la clase ocurrida, 10⁻⁴)); el mismo piso para el base y el ajustado (un ajuste multiplicativo nunca convierte un 0 en positivo).
- **Orígenes**: `backfill` con `start = 150`, uno cada 25 velas, solo los que tienen el horizonte completo observable; etiqueta realizada y bandas = `calibration.evaluate_forecast` (T19) sin cambios; semilla del motor base = la de T19 (0).
- **Bootstrap**: `validation.stats.day_block_ci` (percentiles, 5.000 remuestreos, semilla 0 derivada del rótulo) sobre las diferencias pareadas (base − ajustado) por pronóstico; bloque = día UTC del origen.
- **Mitades (T6)**: orden cronológico, corte en `n // 2`.
- **ECE**: el de `calibration` (curva de 10 intervalos, 3 clases juntas).
- **Tabla por ficha** del informe: descriptiva (R neto de la sombra, fuera de muestra, IC95 % por bloques de día); no es un intento adicional de la puerta: el veredicto T49 sigue siendo por `estrategia@marco@versión`. Lectura honesta con n < 30: «no hay muestra para juzgar».
- **Contextos de 1 h con 500 velas**: la regla de 4 semanas no se evalúa (673 necesarias); el informe lo repite.
- Las huellas de las 9 versiones se declararon en `lineage.json` junto con el código; cambiar `strategies_lit.py` (o `Ind`, `Draft`, `atr_draft`) crea versión nueva, no se mezcla evidencia.

## Anexo 2 — Corrección de forma (2026-10-19, antes de cualquier cálculo con datos reales)
El §B decía que el ajuste se enciende poniendo `enabled: true` en `eim/forecast/versions/lit_tilt_v1.json`. Los archivos de `*/versions/` son inmutables y llevan su SHA-256 en `tests/test_param_versions.py` (T32), así que encenderlo ahí obligaría a reescribir una versión publicada. Corrección sin cambio de fondo: **la definición** (`k` = 0,5, criterios T1–T6, muestra) vive inmutable en `lit_tilt_v1.json` (sin `enabled`) y **la activación** en `eim/forecast/lit_tilt_state.json` (`enabled: false`, versión a la que se refiere). Encenderlo = commit que pone `enabled: true` allí, citando el informe y la decisión del usuario. Ni `k` ni los criterios cambian.
