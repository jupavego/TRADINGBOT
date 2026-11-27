# T221 — Pre-registro: pesos por régimen (`regime_weights`)

> Renumerada el 2026-11-27 (antes T197). Solo cambió el número de tarea; el texto fijado antes de toda cifra es el del commit `a634b8f`.

Fijado el 2026-11-19, **antes de calcular ninguna cifra del banco**, en un commit propio. Nada de
lo que sigue se cambia después de mirar cifras; si un defecto del código obliga a repetir, se
declara en el informe con su motivo, como hicieron T134 (v3) y T166 (v2).

**Modo: SIMULADO.** No toca la síntesis en vivo ni la corrida T31. `regime_weights` sigue `{}` en
`params.py` al terminar, pase o no pase la puerta.

## 1. La pregunta
¿El régimen que ya calcula el agente `regime` (T22) cambia **qué agente acierta**, lo bastante
para que modular los pesos de la síntesis por régimen mejore la señal fuera de muestra, después de
costos?

Una sola pregunta, un solo candidato (la escalera de §4), una sola métrica primaria (§5): **no hay
corrección por multiplicidad** porque no hay más de un intento. Las secundarias son descriptivas y
no deciden nada.

## 2. Datos
`v2/backups/t131_banco` (copia de T131, 2026-11-03, proveedor `binance-futures`): BTCUSDT 1 h,
2023-01-01 → 2026-11-03, 33 666 velas, 0 huecos; funding 4 209 filas. Se copian al `data/` del
worktree solo `timeframe=1h` y `funding`; el almacén vivo no se lee ni se escribe.

Panel de reportes con `eim/analytics/agent_panel.load_or_compute` (el de T44, sin cambiarlo):
calentamiento 500 velas, un instante **cada 4 velas** (`PANEL_STEP` de T44) → ≈ 8 291 instantes.
Agentes sin historia point-in-time (OI, long/short, base, calendario, líderes, arbitraje,
microestructura) salen `no_data`; se declara en el informe cuántas filas quedan así por agente.

## 3. Tramos
Los instantes ordenados se parten por la mitad (`DISC_FRAC = 0.5` de T44):
- **descubrimiento**: primera mitad (≈ 2023-01 → 2024-12, los mismos tramos que midió T44);
- **prueba**: segunda mitad.

La mitad de prueba **no se mira** hasta que los multiplicadores de §4 están calculados y escritos
en el informe. El reparto es por instante, no aleatorio: no hay fuga temporal.

## 4. Los multiplicadores (sin libertad después de este punto)
Para cada régimen g del agente `regime` —`tendencial alcista`, `tendencial bajista`, `rango`,
`alta volatilidad`— y cada agente a **direccional con peso base > 0**:

1. `IC[a,g]` = Spearman entre `sesgo_a × confianza_a` y el log-retorno a 4 velas, sobre los
   instantes de **descubrimiento** etiquetados g y con `status == "ok"` en a;
2. `IC[a]` = lo mismo sobre todo el descubrimiento (sin condicionar al régimen);
3. escalera de tres niveles:
   - `m[a,g] = 1.5` si `IC[a,g] − IC[a] ≥ +0.02`
   - `m[a,g] = 0.5` si `IC[a,g] − IC[a] ≤ −0.02`
   - `m[a,g] = 1.0` en cualquier otro caso, y también si `n[a,g] < 200` muestras.

Escalera y no cociente `IC[a,g]/IC[a]`: el cociente explota cuando `IC[a] ≈ 0`, que es el caso de
casi todos los agentes medidos en T44. Tres niveles y no una función continua porque con 4 regímenes
× ≈ 10 agentes ya hay 40 celdas: una función continua ajustaría ruido celda a celda.

El umbral ±0,02 y el mínimo de 200 muestras se fijan **aquí**, antes de ver ninguna celda.

## 5. Métrica y puerta
Dos variantes de la **misma** síntesis (`eim.synthesis.synthesize`, pesos vigentes de `params.py`):
- **plana**: `regime_weights = {}` (exactamente lo de hoy);
- **por régimen**: `regime_weights` = los `m[a,g]` de §4.

**Primaria**: `ΔIC = IC_por_régimen − IC_plana`, con IC de Spearman entre `sesgo × confianza` de la
síntesis y el log-retorno a **h = 4 velas** sobre la mitad de prueba, muestras **sin solape** (el
panel ya da un instante cada 4 velas, así que h = 4 no solapa). IC95 por **bootstrap emparejado por
bloques** (1 000 remuestreos, bloques de 30 días, la misma semilla para las dos variantes).

**Secundarias, descriptivas**: `ΔIC` a h = 24 (submuestreando a un instante cada 24 velas para no
solapar) y el backtest de T25 con la regla fija de `agents_marginal` (umbral = cuantil 0,8 de
**su propia** variante en descubrimiento, SL 1,5 ATR, RR 2,0, `max_hold_bars` 48, costos de
perpetuo y funding del banco): `ΔSharpe` y `ΔE[R]` neto.

**Entregable 0, la potencia, se calcula antes que §4 se aplique a la prueba**: con la σ de las
diferencias emparejadas medida **en la mitad de descubrimiento** y el tamaño de la mitad de prueba,
la mejora mínima detectable al 80 % de potencia y α = 0,05 a dos colas (`eim/validation/power.py`).

**Puerta de adopción, pre-registrada:**
1. `MDE ≤ 0.01` — si no, veredicto **SIN POTENCIA** y la tarea se cierra en el entregable 0, sin
   calcular nada sobre la prueba (lo que hizo T133 con su cota del oráculo);
2. `ΔIC ≥ +0.01` en la mitad de prueba **con IC95 que excluya 0**;
3. `ΔE[R]` neto `≥ 0` — modular pesos no puede empeorar el resultado con costos.

Las tres se cumplen o **no se adopta**. «No se adopta» significa: `regime_weights` se queda `{}`,
el informe dice por qué y la nota de T221 lo cierra. No hay segunda rejilla, ni otro umbral, ni
otro horizonte: cambiar cualquiera de ellos después de ver la prueba sería otro intento, y esta
tarea solo tiene uno.

## 6. Qué invalidaría la medición
- Que el panel tenga menos de 6 000 instantes utilizables (velas o agentes caídos): se declara y se
  rehace con el tramo que haya, diciéndolo.
- Que `regime` salga `no_data` en más del 20 % de los instantes: sin etiqueta no hay pregunta.
- Que algún régimen no llegue a 200 muestras en descubrimiento: ese régimen entra con
  multiplicador 1,0 en todos sus agentes (es la regla de §4, no una excepción).
