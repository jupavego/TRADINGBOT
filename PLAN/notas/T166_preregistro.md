# T166 — Pre-registro: régimen con modelo de saltos frente a HMM y BOCPD

Fijado el 2026-11-11, **antes de calcular ningún resultado**, en un commit propio. Nada de lo que
sigue se cambia después de mirar cifras; si un defecto del código obliga a repetir, se declara en
el informe.

## Versión 2 (2026-11-11, antes de tocar el tramo de evaluación)

La v1 (commit d5ae85e) se corrigió **antes de calcular ninguna cifra del banco**, por un defecto
que apareció en el ensayo con series sintéticas que se corre para no gastar la cola con un script
roto. El mismo procedimiento que usó T134 con su pre-registro v3: se declara el cambio, su motivo y
que el recuento de intentos no se mueve (siguen 4 candidatos y el Holm sigue siendo sobre 4).

Qué cambia y por qué:

1. **La asignación en línea pasa a ser el filtro del propio modelo.** La v1 declaraba la regla
   voraz s_d = argmin_s ‖x_d − c_s‖² + λ·1[s ≠ s_{d−1}], que exige que **un solo día** pague toda
   la penalización; el DP con el que se ajusta la amortiza entre varios días. Con λ moderado la
   regla voraz **no salta nunca**, así que medía otra cosa que el modelo ajustado. Pasa a ser el
   pase hacia delante del mismo DP (f_d(s) = ‖x_d − c_s‖² + min(f_{d−1}(s), min_{s'} f_{d−1}(s')
   + λ)), que es igual de causal —no mira ningún día posterior— y hace que λ signifique lo mismo
   al ajustar y al evaluar.
2. **La penalización se declara en unidades de los datos, no en un número absoluto.** La v1 fijaba
   λ ∈ {1, 10, 100} sobre rasgos estandarizados; en el ensayo, λ = 10 y λ = 100 dejaban **un solo
   estado**, es decir, dos de los tres intentos eran iguales al suelo sin régimen por construcción
   y no probaban nada. Pasa a λ = c · d̄, con d̄ la distancia cuadrática media al centroide del
   ajuste con λ = 0 (k-means puro) en la misma ventana, y **c ∈ {0,5, 2, 8}**: «cuántos días de
   prueba cuesta saltar». Sigue siendo una rejilla de tres, declarada a priori y sin mirar ninguna
   cifra de evaluación.
3. **El MCS tolera modelos con pérdidas idénticas** (`validation/spa.mcs_with_aliases`): si dos
   modelos dan exactamente el mismo pronóstico, su p del MCS es la misma por definición y se
   copia, en vez de que `arch` divida por una varianza nula y aborte. No cambia ninguna regla.

Nada más se toca: datos, tramos, rasgos, métrica, puerta de potencia y regla de adopción son los
de la v1. Lo que sigue ya está en v2.

**Modo: SIMULADO.** Mide; no toca el agente `regime` en vivo, ni el riesgo, ni la ejecución, ni la
corrida de papel T31. Aunque algo pase, **no se adopta antes del cierre de T31 (2026-11-27)**, y la
adopción sería otra entrega que añade el etiquetador como **métrica** del agente, sin cambiar su
voto (así lo acota la ficha `PLAN/T166.md`).

## Pregunta

`agents/regime` etiqueta hoy con BOCPD (Adams–MacKay, hazard 1/800), que detecta cambios en línea
pero da estados poco persistentes. T77 planea un HMM y T133 dejó el Markov switching sin abrir. Los
**modelos de saltos estadísticos** (Nystrup; Shu, Yu y Mulvey, [arXiv 2402.05272]) dan estados más
persistentes y, en índices de acciones 1990–2023 fuera de muestra, con costos y retardo, baten al
HMM. **No hay prueba en BTC.** La ficha manda compararlos en el banco de T133 **antes de construir
más de un modelo de régimen**:

> ¿Alguno de los dos etiquetadores nuevos condiciona la volatilidad del día siguiente mejor que el
> BOCPD que ya está en producción?

## Licencia de `jumpmodels` (punto 1 del plan de la ficha)

`jumpmodels` 0.1.1 (PyPI, Yizhan Shu) declara **Apache 2.0** por clasificador OSI y en el README
de su repositorio (`info.license` del JSON de PyPI está vacío; la licencia sale del clasificador y
del README). Es permisiva, así que la ficha no obliga a reimplementar. Aun así **se implementa en
NumPy en este repositorio**, por dos razones que no son de licencia:

1. `jumpmodels` exige `scikit-learn`, que **no está en el venv** (comprobado: `find_spec("sklearn")`
   es `None`); añadirlo es una dependencia pesada nueva, con su revisión de T04, para un algoritmo
   de unas sesenta líneas.
2. La comparación exige que el modelo de saltos y el HMM corran sobre **los mismos rasgos, el mismo
   K y el mismo reajuste**; con dos bibliotecas distintas eso no se puede garantizar.

La implementación sigue el algoritmo publicado (descenso por coordenadas alternas: asignación por
programación dinámica con penalización de salto, y recálculo de centroides). No se copia código.

## Datos

- BTCUSDT, **banco de T133** = `backups/t131_banco`: velas de 1 min del 2023-01-01 al
  2026-11-03, 2 019 972 filas, **cobertura 100 %** (`backups/t131_banco/cobertura.md`).
- Un día UTC cuenta si tiene ≥ 90 % de sus velas de 1 min (misma regla que T162 y que
  `paper/ab_conditions.py`). Son ≈ 1 402 días en total.
- **Objetivo de volatilidad:** RV5 del día, Σ de log-retornos de 5 min al cuadrado
  (`forecast/vol_models.daily_series`, el mismo objetivo que T162 y T165).
- **Tramos**, fijados aquí:
  | Tramo | Fechas | Para qué |
  |---|---|---|
  | Ajuste inicial | 2023-01-01 → 2023-06-30 | solo ajuste; no se puntúa |
  | Potencia | 2023-07-01 → 2023-12-31 | estimar la σ de las diferencias de QLIKE **antes** de evaluar |
  | **Evaluación** | **2024-01-01 → último día completo** | la única que decide (≈ 1 036 días) |

## Rasgos (los de T133, conocidos al cierre del día)

T133 no construyó ningún rasgo (su veredicto cerró la línea en el entregable 0), así que «los de
T133» son los del día que usa su banco, `paper/ab_conditions.day_features`, más el objetivo de
volatilidad de T162. Cuatro rasgos por día `d`, todos calculables a las 00:00 del día `d+1`:

1. `ret` — retorno diario logarítmico.
2. `ln_rv` — logaritmo de la RV5 del día.
3. `er` — eficiencia direccional de Kaufman, |cierre − apertura| / Σ|variaciones de cierre|.
4. `rng` — rango relativo del día, (máximo − mínimo) / apertura.

Se estandarizan con **media y desviación expansivas de los días anteriores** (nunca de toda la
muestra), así que ningún rasgo mira al futuro.

## Familia (familia de régimen propia, 4 intentos)

No se suma a la familia de trading de 841 intentos, igual que la de calibración de T162: aquí no se
decide ninguna entrada ni salida. El recuento de rasgos probados de T133 sigue en 0 (no se criba
ningún rasgo: los cuatro están declarados y son los mismos para los tres modelos).

| Id | Modelo | Persistencia | Ajuste |
|---|---|---|---|
| U0 | **Suelo sin régimen:** ĥ = exp(media de ln RV de los días anteriores + v/2) | — | expansivo diario |
| M0 | **Referencia: el BOCPD de hoy** (`agents/regime/bocpd.py` + `labeling.label_bars`, parámetros de `RegimeParams`) sobre la serie diaria | tramo vigente | día a día |
| J1 | Modelo de saltos, K = 2, c = 0,5 | penalización de salto | reajuste cada 20 días |
| J2 | Modelo de saltos, K = 2, c = 2 | penalización de salto | reajuste cada 20 días |
| J3 | Modelo de saltos, K = 2, c = 8 | penalización de salto | reajuste cada 20 días |
| H1 | HMM gaussiano, K = 2, Baum-Welch | matriz de transición | reajuste cada 20 días |

Las tres penalizaciones se declaran **aquí y a priori** como λ = c · d̄ (ver la v2 arriba);
**cada una cuenta como un intento** y entra en el Holm de la familia de 4 candidatos (J1, J2, J3,
H1). No hay elección de c por validación: elegirla mirando el resultado sería un grado de libertad
escondido.

**Sin fuga, por construcción:** los parámetros se ajustan solo con días anteriores al reajuste, y
el estado de cada día se asigna con un **filtro hacia delante** que no mira ningún día posterior
(el modelo de saltos, por el pase hacia delante de su DP; el HMM, por la posterior filtrada;
BOCPD lo es por definición). El reajuste cada 20 días es el mismo paso que T162 usó para su
GJR-GARCH. **M0 se recalcula día a día**, repitiendo el `run()` del agente sobre la historia hasta
ese día: BOCPD no tiene parámetros que ajustar, así que la cadencia de 20 días no le aplica y
dárselo todos los días solo favorece a la referencia.

## Métricas

- **Principal: QLIKE** del pronóstico de la varianza del día siguiente **condicionado al estado**,
  L = RV/ĥ − ln(RV/ĥ) − 1 (Patton 2011, `forecast/vol_eval.qlike`; menor es mejor). Con el estado
  `s` del día `d`, ĥ_{d+1} = exp(m_s + v_s/2), donde `m_s` y `v_s` son la media y la varianza de
  ln RV de los **días anteriores** con estado `s`. Si un estado tiene menos de 20 días previos, se
  usa el estimador incondicional (U0): así un modelo no se beneficia de estados casi vacíos.
- **Descriptivas, no deciden nada:**
  - **Persistencia:** permanencia media, número de cambios y entropía normalizada de la matriz de
    transición (`agents/regime/labeling.stability`).
  - **Condicionamiento del R del banco:** R medio por estado de las operaciones **fuera de
    muestra** de T133 (base M0, la escalera vigente; solo los tramos de prueba de sus 10 pliegues,
    con purga y embargo). Una operación decidida el día `d` hereda el estado del día `d−1`, que es
    el último conocido al entrar. Se informa el ΔR entre el mejor y el peor estado con IC del 95 %
    por bootstrap de bloques de día, y la tabla de potencia de `validation/power.power_row`.
  - **Escala:** la QLIKE del Log-HAR-RV de T162 (M1) sobre los mismos días, **fuera de la familia y
    fuera del MCS**, solo para saber cuánto de lo que hay que explicar explica un etiquetador.

## Potencia a priori, antes de abrir la hipótesis (BACKLOG T161 (3))

Con el tramo de potencia (2023-07-01 → 2023-12-31) se estima la σ de las diferencias emparejadas de
QLIKE (candidato − M0) y se toma **la mayor de los cuatro candidatos** (lo conservador). La mejora
mínima detectable sobre los días de evaluación es

&nbsp;&nbsp;&nbsp;&nbsp;MDE = (z_0,05 + z_0,20)·σ / √n_eval = 2,4865·σ / √n_eval.

**Puerta declarada: la hipótesis se abre solo si MDE ≤ 0,020** en unidades de QLIKE, que es el
orden de los efectos que T162 (−0,032) y T165 (−0,021) sí encontraron. Si la historia disponible no
alcanza, la tarea **se cierra con ese veredicto** y no se calcula ni el MCS ni ninguna p: forzar un
resultado con poca potencia es exactamente lo que T161 dejó prohibido.

Para la pregunta del R, la potencia se declara con los números publicados de T134: σ de las
diferencias emparejadas 0,352 R y objetivo Δ = +0,05 R (el único efecto que T134 encontró,
+0,0493 R), de donde n ≈ (1,645 + 0,8416)²·0,352²/0,05² ≈ **306 operaciones**; el banco aporta
29 828 fuera de muestra, así que esa pregunta sí tiene potencia y se responde.

## Regla de adopción (se aplica tal cual)

Un candidato Mk ∈ {J1, J2, J3, H1} **pasa** si se cumplen las tres:

1. **Model Confidence Set** al 10 % sobre las pérdidas QLIKE de {U0, M0, J1, J2, J3, H1}
   (`validation/spa.mcs_with_aliases`, bootstrap estacionario, bloque de Politis-White, 5 000
   repeticiones, semilla 166): Mk está dentro y **M0 queda fuera**.
2. **Mejora frente a M0:** la diferencia media de QLIKE (Mk − M0) tiene un IC del 95 % por
   bootstrap estacionario que **excluye 0 por debajo** (`validation/spa.mean_diff_test`) y su p
   unilateral **ajustada por Holm en la familia de 4** es < 0,05.
3. **Mejora frente a U0:** la diferencia media de QLIKE (Mk − U0) tiene un IC del 95 % que excluye
   0 por debajo. Sin esto, el «régimen» no aporta nada sobre no tener régimen y no se propone.

Si pasan varios, se propone el de menor QLIKE media. **Si no pasa ninguno, la línea se cierra**: el
agente `regime` sigue con BOCPD, no se construye ningún modelo de régimen más y el informe lo dice
así. Ni la persistencia ni el ΔR por estado pueden por sí solos hacer que algo pase: son
descriptivas, y una permanencia más larga sin condicionamiento no es información.

## Lo que esta tarea no hace

- No cambia el voto del agente `regime` (que además está excluido del voto en síntesis desde T22),
  ni la síntesis, ni los perfiles, ni el riesgo, ni la ejecución.
- No mide HMM para HFT (T77/T81), que está fuera de alcance por la ficha.
- No reabre M4 ni ninguna salida adaptativa: T133 la descartó y T134 no adoptó ninguna salida. El R
  por estado se mide como **descripción** del banco, no como regla.
- No instala `jumpmodels` ni `scikit-learn` ni `hmmlearn`; sin dependencias nuevas (numpy, scipy y
  el extra `stats` con `arch`, ya en uso desde T161).
