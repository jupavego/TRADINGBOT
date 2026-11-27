# Cruce: «Regime-Aware Trading» (artículo del usuario, 2026-11-19) frente a lo construido

El usuario pegó en el chat un texto que propone un **Range Intelligence Engine** para mercados
laterales: siete módulos, ocho teorías matemáticas, cinco repositorios y una bibliografía. Esta
nota deja por escrito qué de eso ya existe en EIM, qué ya se midió y se descartó, y qué falta de
verdad, para no repetir la comparación en la próxima sesión.

Veredicto corto: **cuatro de las siete áreas están en producción**, una está a medias y dos
siguen pendientes dentro de la fase HFT (T79–T86). Y las dos piezas centrales que el texto
propone como novedad —HMM de régimen y selección de estrategia por régimen— **ya se midieron
con pre-registro y no pasaron** (T166 sin potencia, T133 descartada en su cota del oráculo).

## 1. Las siete áreas

| Área del texto | Estado en EIM | Dónde |
|---|---|---|
| 1. Range Detection | ☑ en producción | T12, `eim/agents/levels/` (pivotes, zonas S/R, `channel.py`, ATR); Donchian, ADX, Bollinger y ATR en `eim/indicators/` y `agents/technical`; reglas de Murphy/Kaufman en `agents/literature` |
| 2. Mean Reversion | ◐ solo reglas, sin modelo | `ind_rsi_reversion`, `ind_bb_reversion` (`eim/paper/strategies_ind.py`), agente `vwap`. **No hay** Ornstein-Uhlenbeck, z-score, half-life de reversión ni cointegración |
| 3. Regime Detection | ☑ en producción, y ya medido | T22, `eim/agents/regime/` (BOCPD Adams-MacKay Normal-Gamma propio, etiquetas tendencial alcista/bajista/rango/alta volatilidad, permanencia y entropía); T133 y T166 lo midieron |
| 4. Market Microstructure | ☑ en producción | T23 + T104 + T78: recolector `depth@100ms` y `bookTicker`, agente con OFI, delta agresor (CVD), desequilibrio top-10, divergencia precio/CVD, Parkinson y Garman-Klass; funding y OI en `derivatives`; liquidaciones con su agente. **Hawkes: no** |
| 5. Market Making | ☐ pendiente | Es **T82** (direccional + Avellaneda–Stoikov + selector de estado), bloqueada por T79 (simulador de libro con latencia, cola y fills), T80 y T81 |
| 6. Machine Learning | ◐ auditado, poco adoptado | Freqtrade/FreqAI, Hummingbot y Qlib/RD-Agent auditados (T56–T59, T113); `forecast/kronos_engine.py`. Sin RL ni XGBoost/LightGBM: `scikit-learn` no está en el venv (por eso el HMM de T166 va en NumPy). River y `ruptures` en BACKLOG, condicionados a deriva demostrada |
| 7. Execution Intelligence | ☑ lo más desarrollado | T25 (costos de perpetuos), banco de latencia de T77 (reacción p99 310 ms, Python 8,8 % del presupuesto), `eim/hft/cost_bound.py`, libro de costo vivido y A/B maker-taker (T143), puerta de costo por perfil y marco (T179, desplegada). **Falta** probabilidad de fill y posición en cola → es T79 |

## 2. Lo que ya se midió y no pasó

- **T166** (modelo de saltos frente a HMM gaussiano y BOCPD): **SIN POTENCIA**. Con 1 037 días de
  evaluación, la mejora mínima detectable de QLIKE es 0,146 frente a la puerta pre-registrada de
  0,020; harían falta ≈ 151 años. Dato útil contra el texto: el **HMM es el peor de los tres en
  persistencia** (permanencia 2,6 días y 393 cambios, frente a 51,9 días y 19 cambios del modelo
  de saltos), que es justo el defecto que el propio texto señala al final (confundir ruido con
  cambio de régimen y pagar comisiones por ello).
- **T133** (¿algún rasgo anticipa tendencia o lateral?): **descartada en su entregable 0**. Con la
  etiqueta ex post —información futura perfecta— la esperanza sube de −0,154 a −0,093 R y **sigue
  perdiendo**; no cumplió los criterios 2 y 3. Conocer el régimen elige qué salida usar, no cambia
  la forma de las operaciones.

## 3. Repositorios y bibliotecas del texto: todos ya auditados

| Propuesta | Estado |
|---|---|
| HftBacktest | Auditado en T77; solo aislado (exige `numpy<2.3`). El formato `eim_hft_events` de T78 comparte su registro de 64 B, pero los códigos `ev` son propios: el contraste necesita traducción (BACKLOG T78 (4)) |
| Hummingbot | Portados `bollinger_v1` y `macd_bb_v1` a `eim/bots/hb_directional.py` (T57/T58); `supertrend_v1`, `dman_v3` y `bollinger_v2` fuera por ahora |
| NautilusTrader | T25 decidió **motor propio**; revisado otra vez en el segundo artículo de repos (2026-10-28) sin cambiar la decisión |
| Freqtrade / FreqAI | Referencia aislada en `D:/eim-bots/ft-env` (GPL, nunca se copia código); modo B del escuadrón |
| vectorbt | Solo como oráculo de contraste; el apalancamiento de futuros es de la versión PRO y arrastra Commons Clause (BACKLOG) |
| hmmlearn | Fuera del extra `hft` a propósito (mantenimiento limitado); T166 implementó el HMM en NumPy para garantizar los mismos rasgos que el competidor |
| `ruptures`, River, QuantStats | BACKLOG T77/T85: solo con deriva demostrada o necesidad medida |
| Kelly | Ya está, y más conservador que el texto: fraccionado sobre el **límite inferior** del IC de E[R] (`eim/paper/kelly.py`, T136) |
| Ornstein-Uhlenbeck, Avellaneda-Stoikov, Hawkes, cointegración | Sin código. A-S es T82; los otros tres no tienen tarea |

## 4. Lo que de verdad falta

1. **T79, el simulador a nivel de libro** (latencia, cola, fills). Sin él no es medible ninguna
   estrategia de rango con órdenes límite, ni Avellaneda-Stoikov. La cota de T77 ya acota el
   terreno: **por debajo de 10 s no paga ni con previsión perfecta** → horizonte mínimo 30 s.
2. **`regime_weights` vacío.** El mecanismo existe (`eim/synthesis/synth.py:25` multiplica el peso
   de cada agente por el multiplicador de su régimen) pero `SynthesisParams.regime_weights` es
   `{}` desde T22: nunca se calibró. Es el único punto donde el régimen que EIM ya calcula podría
   cambiar una decisión sin construir nada nuevo. → **T221**.

## 5. Contraste de fondo

El texto propone añadir seis motores. La respuesta que este proyecto le ha dado a «el mercado está
lateral y pierdo» ha sido la contraria y está medida: **cerrar el marco que no paga** (T179 cierra
agresivo@15m con 0,173 R de costo) y dejar de destruir ventaja antes de inventar más. Con E[R]
neto en −0,15 R, un motor nuevo sin la puerta de edge delante solo añade formas de perder más
rápido. Nada de esta nota cambia el alcance de T145 (solo análisis).
