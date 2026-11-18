# T164 — Carry y momentum transversales (`transversal_v1`)

**Modo: ANÁLISIS.** Generado 2026-11-18T03:26:41Z con el pre-registro `PLAN/notas/T164_preregistro.md`, congelado antes de esta corrida.

## Universo y cobertura

- Perpetuos USDT en `universe.json`: 659 ({'TRADING': 522, 'SETTLING': 136, 'PENDING_TRADING': 1}). Los retirados hace años no están: **sesgo de supervivencia** (T181).

## Puerta de potencia (§4, sin retornos)

- Semanas con ≥ 30 elegibles: 323 desde 2020-09-07; evaluables tras 26 de calentamiento: **5.69 años** frente a 5.1 necesarios → **PASA**.

## Medición única (combinada, m = 1, z = 1,645)

- Semanas medidas: 310 (2020-12-07 → 2026-11-09).
- **t de Newey-West = 0.81** (p unilateral 0.2076) → **NO PASA**.
- Beta semanal frente a BTC (en retorno; neutral si |β| < 0,3): carry +0.037 (neutral), momentum -0.038 (neutral) · correlación de la combinada con BTC +0.07 · correlación carry–momentum +0.17.

| Cartera | Semanas | Media semanal | Sharpe anual |
|---|---|---|---|
| carry | 323 | +0.262 % | +0.77 |
| momentum | 323 | +0.120 % | +0.24 |
| combinada | 310 | +0.040 σ | +0.35 |

Carry y momentum se informan; **solo la combinada se juzga** (◆ del usuario).
La combinada está en unidades de volatilidad (escala de 26 semanas): su media no es un retorno en %, su Sharpe sí se compara.

## Notas de la corrida (2026-11-18)

- **Una sola medición.** El informe se generó dos veces seguidas con la misma prueba y el mismo resultado
  (t = 0,81). La primera, a las 03:24:51 UTC, publicó una beta de la combinada de +0,754 («no neutral») porque
  comparaba una serie en unidades de volatilidad con retornos de BTC. La segunda mide la beta de cada cartera
  en retorno y de la combinada solo da la correlación. No cambia nada de lo que se juzga.
- **Lectura.** La hipótesis pre-registrada (la combinada) **no pasa**: no hay ventaja demostrada en la sección
  cruzada con estas reglas y esta historia. El carry por separado da Sharpe neto +0,77 y es neutral al mercado,
  pero **no era la hipótesis juzgada**: elegirlo ahora sería mirar el resultado y escoger. Además, el sesgo de
  supervivencia probablemente lo favorece (faltan los retirados hace años, y la pata larga del carry compra
  monedas con funding negativo, que son las que más se retiran). Confirmar un Sharpe de 0,77 hacia adelante,
  con una prueba de una sola hipótesis, pediría ((1,645 + 0,842) / 0,77)² ≈ **10,4 años**.
- Si se quisiera seguir esta pista, sería **otro pre-registro** con su propia familia, medido hacia adelante
  y con los retirados recuperados (`data.binance.vision`, ◆ de descarga): BACKLOG T164.
