# T164 — Pre-registro `transversal_v1` (congelado el 2026-11-18, antes de mirar ningún retorno)

**Modo: ANÁLISIS.** Mientras se escribía esto, T181 descargaba la historia del universo. Nadie ha
calculado ni mirado un retorno de ninguna cartera transversal. Este archivo se confirma en un commit
anterior a cualquier cálculo de rendimiento. Cambiar algo de lo que sigue es otro pre-registro y
otro intento.

## 1. Universo en cada fecha de rebalanceo `t` (lunes 00:00 UTC)
- Perpetuos USDT de `data/universe_perps/` (T181), dados de alta hace **≥ 60 días**, con **≥ 28 de
  las 30** velas diarias previas y una mediana de volumen en USDT (volumen × cierre) en 30 días
  **≥ 5 M USDT**.
- Se excluyen las bases estables o de moneda (USDC, BUSD, TUSD, FDUSD, DAI, USDP, EUR, GBP, AEUR).
- Solo se usa información ≤ `t`. Una fecha cuenta si hay **≥ 30 elegibles**.

## 2. Señales y carteras (semanales, neutrales en dólares)
- **Carry (C):** funding medio de los últimos 7 días (normalizado a 8 h si el intervalo es otro)
  dividido por la volatilidad de 30 días de los retornos diarios. **Corto** en el quintil superior
  (cobra funding) y **largo** en el inferior.
- **Momentum (M):** retorno de 14 días hasta `t`. **Largo** en el quintil superior y **corto** en
  el inferior.
- **Pesos:** inverso de la volatilidad de 30 días dentro de cada pata; cada pata suma 1 de nocional
  (capital = 1 por pata, sin apalancamiento adicional). Tenencia de una semana.
- **P&L de la semana:** retornos de precio de las dos patas + funding real cobrado o pagado en cada
  liquidación − costos.
- **Costos:** 5 pb de comisión de tomador y 5 pb de deslizamiento por lado sobre el nocional que se
  rota (10 pb por lado, el doble del deslizamiento base de BTC por la menor liquidez de las altcoins).

## 3. Unidad, prueba y familia
- **Unidad:** retorno neto semanal de cada cartera.
- **Prueba:** media semanal > 0, unilateral, con errores de Newey-West (4 retardos). **Familia propia
  de T164** (◆ del usuario, 2026-11-18): los 841 intentos de T49/T139 fueron sobre BTC y ETH, y la
  sección cruzada nunca se ha mirado en el proyecto. Holm dentro de la familia a α = 0,05.
- **Neutralidad:** beta semanal frente a BTC, con |β| < 0,3 para llamarla neutral (se informa).
- **Riesgo declarado:** el carry se comprimió desde 2024 y fue negativo en 2025 (arXiv 2510.14435).
  Un carry alto predice caídas (BIS WP 1087).

## 4. Puerta de potencia (se aplica ANTES de calcular ningún retorno)
Regla de la casa (T163): el Sharpe mínimo a detectar es la **mitad** del publicado.
- **M:** +2,1 % semanal con t 3,70 después de 2020 (Liu, Tsyvinski y Wu, actualización), sobre
  ≈ 4,5 años → Sharpe anual bruto ≈ 1,74 → **S_min = 0,87**.
- **C:** IC funding/volatilidad +0,041 (informal) → Sharpe ≈ IC · √(N · 52) · TC con N = 150 y una
  transferencia de 0,5 → ≈ 1,8 → **S_min = 0,90**.

Años necesarios con potencia 0,8: `T = ((z + 0,842) / S_min)²`.

| Elección | z | T para M | T para C | T para la combinada (ρ = 0 / 0,3) |
|---|---|---|---|---|
| **A. Familia propia m = 2 (C y M por separado)** — elegida | 1,960 | 10,4 años | 9,7 años | — |
| B. Solo carry, m = 1 | 1,645 | — | 7,6 años | — |
| C. Una sola hipótesis: la **combinada** C + M a riesgo igual, m = 1 | 1,645 | — | — | 3,9 / 5,1 años |

La combinada a riesgo igual tiene S = (S_C + S_M) / √(2 · (1 + ρ)), con ρ la correlación entre C y M,
que **se fija aquí en 0,3** como supuesto (con ρ = 0,3, S = 1,10). En cripto se espera baja o negativa: el funding alto se concentra en las
ganadoras recientes, que M compra y C vende.

**La historia disponible se calcula con el universo de §1** (fechas de alta y volumen, nunca con
retornos): número de semanas con ≥ 30 elegibles, en años. Por las fechas de alta, se espera
≈ 5,8 años (2021-01 → 2026-11).

**Decisión congelada:** se mide solo la hipótesis cuya T quepa en la historia disponible. Con A,
ninguna cabe (10,4 y 9,7 años frente a ≈ 5,8). **Se declara SIN POTENCIA, no se calcula ningún
retorno y no se gasta el intento**, como en T163 y T166, salvo que el usuario cambie a C (◆ abierta
el 2026-11-18). En ese caso la combinada se mide una sola vez, con todo lo de §1–§3.

## 5. Informe
`v2/reports/t164_transversal.md` + JSON: universo por fecha (con la cobertura de los retirados según
`universe.json`), la puerta de potencia con sus cifras y, solo si pasa, el veredicto.
