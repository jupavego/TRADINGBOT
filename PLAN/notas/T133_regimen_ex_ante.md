# T133 — Régimen ex ante: ¿algún rasgo anticipa tendencia o lateral?

**Modo: SIMULADO.** Fase 22, tras T131. **Veredicto: M4 se descarta.** La tarea se cierra en su
entregable 0 —la cota del oráculo (E6)— sin construir ni un rasgo, que es exactamente lo que su
ficha manda: «Si incluso así M4 no cumpliría los criterios 1–3 de §5.4 frente a M0 y M1, **M4 se
descarta** sin seguir».

Informe de cifras: `v2/reports/t133_oracle.md` (+ `.json`). Nada tocado en vivo.

## 1. La pregunta y por qué se contesta así

T111 vio que la escalera gana en los días laterales y la salida A en los de tendencia, pero la
etiqueta de régimen que se conoce **al entrar** no separa los casos. La tentación es construir
rasgos (Efficiency Ratio, ADX, cociente de varianzas, vida media de Ornstein–Uhlenbeck, BOCPD…),
medir su AUC y ver si predicen. E6 obliga a hacer antes una pregunta más barata y más dura:

> ¿Cuánto daría M4 **si el régimen se conociera con certeza**?

Porque un predictor real recupera solo una parte de ese techo. Si el techo ya no alcanza los
criterios de adopción, construir el predictor es trabajo perdido por definición, y además con el
riesgo de encontrar señal por azar entre decenas de pruebas (E7).

## 2. Cómo se calculó

Con el banco de T131, sobre la copia reconstruida (2 019 972 velas de 1 min desde 2023) y **solo
con los tramos de prueba** de sus 10 pliegues, con su purga y su embargo de 200 h: 60 720 ideas,
45 822 emparejadas, **29 828 operaciones fuera de muestra** por serie.

Se compararon dos cotas, y conviene no confundirlas:

- **`M4_oraculo`** — la que pre-registra E6. Con la etiqueta **ex post** del día
  (`ab_conditions`: eficiencia direccional del día en tercios) se toma **M0 en los días laterales
  y M1 en los de tendencia**. Los días «intermedio» (14 466 de 45 822) y los 42 sin etiqueta van a
  la escalera, que es la salida vigente; el mapa queda declarado en el script y en el informe.
  Es el techo de un **selector de régimen perfecto**.
- **`M4_envolvente`** — contexto, **no** una cota de M4. En cada entrada toma la mejor de las dos
  salidas sabiendo ya cómo acabó. No es un selector de régimen: acierta operación a operación, no
  día a día.

## 3. Las cifras

| Serie | n | Acierto | E[R] | Gan. media | Pérd. media | Cociente | PF | DD máx. R | CVaR 95 % |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `M0` escalera | 29 828 | 76,1 % | −0,154 | +0,127 | −1,048 | 0,12 | 0,386 | 4 591 | −1,350 |
| `M1` TP/BE+/tiempo | 29 828 | 49,2 % | −0,152 | +0,843 | −1,115 | 0,76 | 0,731 | 4 560 | −1,394 |
| **`M4_oraculo`** | 29 828 | 67,8 % | **−0,093** | +0,386 | −1,101 | 0,35 | 0,737 | 2 812 | −1,373 |
| `M4_envolvente` | 29 828 | 78,1 % | +0,210 | +0,586 | −1,131 | 0,52 | 1,848 | 45 | −1,350 |

Criterios 1–3 de §5.4 del **oráculo por día**:

| Base | ΔE[R] | IC 95 % (bloques de día) | 1 (Δ e IC) | 2 (cociente y PF) | 3 (DD y CVaR) | ¿Cumple? |
|---|--:|---|---|---|---|---|
| `M0` | +0,0606 | [+0,0453, +0,0758] | sí | **no** | **no** | **NO** |
| `M1` | +0,0592 | [+0,0461, +0,0728] | sí | **no** | sí | **NO** |

Por qué falla, con nombre y apellido:

- **Criterio 2, frente a M0:** el cociente ganancia media / pérdida media sube de 0,12 a **0,35**,
  pero el criterio exige **≥ 0,50**. Conocer el régimen del día decide *cuál* de las dos salidas
  usar, no cambia la forma de las operaciones: las perdedoras siguen costando ~1,1 R.
- **Criterio 2, frente a M1:** el PF llega a **0,737** y se le exige ≥ 1,15 × 0,731 = **0,841**.
- **Criterio 3, frente a M0:** el CVaR 95 % empeora, de −1,350 a **−1,373**. El oráculo mejora la
  media y el drawdown (4 591 → 2 812 R), pero no la cola.
- **Y sobre todo:** el oráculo **sigue perdiendo**, −0,093 R por operación. Un selector perfecto de
  régimen no convierte estas entradas en rentables; solo pierde un 40 % menos.

## 4. Por qué la envolvente no salva nada

La envolvente sí cumple los tres criterios (E[R] +0,210, PF 1,85). Es tentador leerlo como «hay
techo», y es falso: su **drawdown cae de 4 591 R a 45 R**. Esa cifra es el termómetro de cuánta
información futura usa. Eligió M0 en 28 794 entradas y M1 en 17 028, es decir, acertó la mejor de
las dos casi siempre, operación a operación. Ningún predictor de régimen —ni perfecto— puede hacer
eso: el régimen es una propiedad del **día**, no de la operación.

Dicho de otro modo: la envolvente mide que estas entradas serían rentables **si se supiera de
antemano el resultado de cada una**, lo cual no es una cota de M4 sino una medida de lo lejos que
está el sistema de tener ventaja. Por eso el veredicto de `oracle.verdict()` se juzga con el
oráculo por día, y una prueba lo fija
(`test_the_verdict_judges_the_day_oracle_and_not_the_envelope`).

## 5. Qué se hizo y qué no

- **Entregable 0 (cota del oráculo): hecho.** Es el que cierra la tarea.
- **Entregables 1, 2 y 3 (etiqueta objetivo, rasgos, walk-forward con AUC/Brier): NO se hicieron**,
  por decisión de la propia ficha. **Número de pruebas estadísticas sobre rasgos: 0.** No hubo
  cribado de Benjamini-Hochberg ni confirmación por Holm o Romano-Wolf porque no se probó ningún
  rasgo: el techo se midió primero y cerró la puerta. Eso mantiene limpio el recuento de intentos
  de la fase (E7) y el Sharpe deflactado.
- **Entregable 4 (veredicto): M4 se descarta**, con sus cifras arriba.
- Sin dependencias nuevas: todo con numpy. `statsmodels` no llegó a hacer falta, así que la ◆5 de
  T129 (Markov switching tras la revisión de T04) **queda sin abrir**.
- El agente `regime` no se tocó (fuera de alcance).

## 6. Qué significa para la fase 22

- **M4 sale del plan.** T134 ya no tiene que medirla, y su rejilla pre-registrada baja de 107 a
  **105 intentos** (M4 aportaba 2). El pre-registro `prereg_t131_v2` **no se edita**: la rejilla
  declarada se conserva tal cual y M4 queda marcada como descartada en este informe y en
  `PLAN/STATUS.md`. Si T134 quiere recontar intentos, lo hará con una versión nueva.
- **No afecta a T132.** M2, M3, M5, M6, M7, M8 y S1 cambian la **geometría** del stop (distancia,
  unidad de volatilidad, ancla de estructura, fases), no eligen entre las dos salidas de hoy. Esta
  cota no dice nada sobre ellas.
- **Refuerza lo que ya decía T131:** con PBO 0,46, todas las variantes en E[R] negativo y ahora un
  oráculo de régimen que tampoco cruza a positivo, la evidencia apunta una y otra vez al mismo
  sitio: **el problema está en la entrada** (T27, T49, T111). La fase 22 puede mejorar la salida,
  pero no va a hacer rentable un conjunto de entradas sin ventaja.

## 7. Abierto

- Nada de T133 queda a medias: la tarea se cierra por donde su ficha dice que se cierra.
- Si en el futuro cambian las **entradas** (T27/T49) y vuelven a tener ventaja, esta cota hay que
  **recalcularla** antes de reabrir M4: es específica de este conjunto de entradas y de estas dos
  salidas. El script es `v2/scripts/t133_oracle.py` y tarda ~70 s.
- El cribado por FDR y la confirmación de E7 siguen **sin usar** en el código del proyecto; si
  T132 o T134 los necesitan, hay que implementarlos (hoy solo existen Holm y Romano-Wolf, en
  `eim/paper/exits/stats.py`).
