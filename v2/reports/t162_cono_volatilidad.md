# T162 — Volatilidad del día siguiente para el cono: HAR, GARCH estimado y ACI

**Modo: SIMULADO.** Mide; no toca el forecaster en vivo. Aunque haya un modelo que pasa, no se adopta antes del cierre de T31 (2026-11-27).

Pre-registro: `PLAN/notas/T162_preregistro.md`, commit `ebaae60`, anterior a todo resultado. Datos: `backups/t139_banco`, BTCUSDT · comando: `python scripts/t162_volatilidad.py --data backups/t139_banco` · cifras en `reports/t162_cono_volatilidad.json` · 2 135 días evaluados (2021-01-01 → 2026-11-05) y 1 040 en 2024–2026; 1 día excluido por cobertura < 90 %.

## En una línea

**M1 (Log-HAR-RV) pasa las tres condiciones de la regla pre-registrada** y es el único modelo que queda en el Model Confidence Set. Pero su ventaja está en pronosticar la **varianza realizada**, no en la **distribución del retorno** que dibuja el cono: ahí empata con el GARCH fijo actual (mismo CRPS). Recomendación: adoptarlo **después de T31**, junto con ACI, y medir en paralelo en vivo si mejora las bandas dibujadas.

## Resultado frente a la regla

| Modelo | QLIKE media (todo) | 2024–2026 | Δ frente a M0 (IC95 %) | p Holm | En el MCS (p) | Cobertura 80 % con ACI (todo / 2024–26) | ¿Pasa? |
|---|---|---|---|---|---|---|---|
| M0 · GARCH fijo del cono (referencia) | 0,337 | 0,287 | — | — | **no** (0,005) | 80,1 % / 80,2 % | — |
| **M1 · Log-HAR-RV** | **0,305** | **0,264** | **−0,032 (−0,051 … −0,014)** | **0,004** | **sí (1,000)** | 80,1 % / 80,3 % | **sí** |
| M2 · GJR-GARCH-t diario | 0,415 | 0,369 | +0,078 (+0,028 … +0,120) | 1,000 | no (0,000) | 80,2 % / 80,5 % | no |
| M3 · media de M1 y M2 | 0,338 | 0,304 | +0,001 (−0,036 … +0,032) | 1,000 | no (0,016) | 80,2 % / 80,4 % | no |

- **Condición 1 (MCS):** solo M1 sobrevive al 10 %; M0 queda fuera. ✔
- **Condición 2 (mejora frente a M0):** QLIKE un **9,6 % menor**, IC que excluye 0 y p de Holm 0,004 en la familia de 3. ✔
- **Condición 3 (cobertura con ACI):** 80,1 % en todo el tramo y 80,3 % en 2024–2026, dentro de 80 ± 2 pp. ✔

El bloque medio del bootstrap (Politis-White) salió en 1,4 días.

## El matiz: la varianza mejora, el retorno no

QLIKE puntúa el pronóstico de la **varianza realizada** del día (RV con retornos de 5 min). Las métricas secundarias, que el pre-registro dejó como descriptivas, miran otra cosa:

| Modelo | RV media / pronóstico | CRPS del retorno diario | Cobertura 80 % sin ACI | PIT: deciles centrales (5.º–6.º) |
|---|---|---|---|---|
| M0 | 1,21 (se queda corto) | 0,01534 | 81,5 % | 0,143 · 0,132 |
| M1 | 1,01 (insesgado) | 0,01534 | 84,2 % | 0,155 · 0,135 |
| M2 | 0,75 (se pasa) | 0,01571 | 89,1 % | 0,185 · 0,160 |

- **Buena parte de la ventaja de M1 es de nivel:** acierta la media de la RV (cociente 1,01), mientras M0 la subestima un 21 % y M2 la sobrestima un 33 %. QLIKE castiga el sesgo, y M1 es el único que se ajusta directamente a la RV.
- **Para la distribución del retorno, empatan:** el CRPS de M0 y M1 es idéntico hasta la cuarta cifra. Sin ACI, la banda del 80 % de M1 cubre de más (84 %) y la de M0 casi bien (81,5 %).
- **El PIT de todos tiene joroba central y colas finas:** la predictiva normal es demasiado ancha en el centro y demasiado estrecha en las colas. Es la cola gruesa de BTC, no un defecto de un modelo concreto. El motor base ya la recoge en parte al remuestrear formas de vela reales en vez de usar una normal.
- **ACI hace su trabajo:** cualquiera de los cuatro queda en 80 ± 0,5 % de cobertura con ACI. Pero la **peor ventana de 90 días** sigue lejos: 71 % para M0 y 90 % para M1. ACI garantiza el largo plazo, no cada trimestre.

## Recomendación

1. **Adoptar M1 como σ del cono tras el cierre de T31**, con ACI sobre las bandas: cumple la regla, es insesgado, cuesta casi nada (ecuaciones normales acumuladas) y no añade dependencias (`harrv.py` ya existía; el Log-HAR es NumPy).
2. **No esperar mejores bandas por sí solo:** en la distribución del retorno empata con lo actual. El beneficio práctico es un σ bien centrado para los stops y el tamaño, y que ACI corrija la cobertura sin que haya que recalibrar a mano.
3. **La entrega de adopción** (otra tarea, tras 2026-11-27) debe medir en paralelo y en vivo el pinball y la cobertura del cono de 1 h con M1 + ACI frente al actual antes de cambiar lo que se dibuja.
4. **GJR-GARCH diario (M2) se descarta**, y con él la combinación: sobrestima la varianza y empeora todo.

## Qué se añadió al código

- `eim/forecast/vol_models.py`: `daily_series` (RV5, retorno y cobertura por día), `m0_fixed_garch` (la recursión del motor base agregada a 24 h), `m1_log_har` (reajuste diario sin fuga) y `m2_gjr_garch` (con `arch`).
- `eim/forecast/vol_eval.py`: QLIKE, CRPS normal cerrado, PIT, banda fija, ACI y la peor ventana.
- `eim/validation/spa.py`: `mcs_losses` (MCS sobre pérdidas) y `mean_diff_test` (IC y p de una diferencia de pérdidas por bootstrap estacionario).
- `scripts/t162_volatilidad.py`.
- Pruebas: cada modelo se prueba **sin fuga** (cambiar el futuro no cambia el pronóstico de hoy), la fórmula cerrada del GARCH fijo, el CRPS frente a la integral numérica y que ACI repara una banda mal escalada.

## Límites

- **Kronos no se midió:** necesita torch, que el venv no tiene; queda en BACKLOG con su aviso de memoria.
- **Solo BTCUSDT.** ETH queda para la entrega de adopción.
- **Se mide a 1 día**, el horizonte del cono, no vela a vela. Que M1 sea mejor a 1 día no garantiza que lo sea dentro del día.
- **Los diagramas de Murphy** quedan en BACKLOG, como fijó el pre-registro.
