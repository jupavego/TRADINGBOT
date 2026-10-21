# Calibración del deslizamiento del bróker simulado (2026-10-20)

**Estado:** informe. No cambia ningún parámetro: `CostParams` sigue igual hasta que se decida.

## Qué se midió
Se recorrió el libro real de BTCUSDT (`data/micro/top`, 6.000 instantáneas muestreadas del 2026-10-20, 250 archivos horarios) comprando a mercado 1.500, 15.000 y 150.000 USDT, y se midió el precio medio de llenado frente al precio medio (mid).

| Notional | Mediana | p90 | p99 | Máximo |
|---|---|---|---|---|
| 1.500 USDT | 0,01 pb | 0,01 pb | 0,01 pb | 0,37 pb |
| 15.000 USDT | 0,01 pb | 0,01 pb | 0,01 pb | 0,50 pb |
| 150.000 USDT | 0,01 pb | 0,01 pb | 0,01 pb | 0,34 pb |

El primer nivel del libro suele tener 5–25 BTC (≈ 0,4–2 M USDT): ninguna operación del bróker simulado lo atraviesa.

## Qué supone el modelo hoy (`CostParams`, `eim/paper/engine.py::_slip`)
`slip = 1 pb + 0,10 × (h − l)/o` de la vela de 15 m de ejecución, en la entrada y en cada salida por SL/BE/TIEMPO. Con rangos típicos de 15 m (0,2–0,4 %) son ≈ 3–5 pb por lado.

## Lectura
- Para llenados a mercado en el tamaño del bróker, el modelo sobrestima el deslizamiento de libro en ~2–3 órdenes de magnitud.
- **Pero** esta medida es el deslizamiento *estático* del libro. No incluye latencia ni el movimiento adverso durante picos de volatilidad, que es lo que pretende capturar el término de rango; sobre todo en SL (stop de mercado que se activa cuando el precio ya corre).
- En el libro de papel el deslizamiento ≈ las comisiones (147 vs 147 USDT en Moderado): es la mitad de la fricción total.

## Propuesta (pendiente de decisión)
1. Entradas límite y TP (límite): deslizamiento 0.
2. Entradas a mercado: separar `slip_base_bps` (≈ 0,1 pb medido, con margen) del término de volatilidad.
3. Salidas por SL: conservar un término de volatilidad (no hay medición de stops en picos todavía).
4. Para fijar (3) hace falta medir el movimiento del precio en los ~1–3 s posteriores a las activaciones de SL en `data/micro/trades`.

Efecto esperado: baja el costo medio por operación y deja de rechazar ideas por «costo estimado > máximo»; **no crea ventaja**: el control aleatorio sigue en −0,20 R/op.
